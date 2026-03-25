"""
ShieldRunner — the core scan engine.

Execution order per shield:
1. Pattern matching (sync, fast) — regex and keyword patterns from shield.yaml
2. Logic module (async, optional) — shield's logic.py for complex detection
3. Collect findings, resolve effective action
"""
from __future__ import annotations

import logging
import re
from typing import Any

from aigate.shields.loader import import_logic_module, load_shields
from aigate.shields.models import (
    ACTION_RANK,
    ActionType,
    Finding,
    PatternDefinition,
    ScanContext,
    ScanSummary,
    ShieldDefinition,
    ShieldResult,
    _extract_text,
    resolve_effective_action,
)

logger = logging.getLogger(__name__)


class ShieldRunner:
    def __init__(self, shields_dirs: list[str]) -> None:
        self.shields_dirs = shields_dirs
        self._shields: dict[str, ShieldDefinition] = {}
        self._logic_cache: dict[str, Any] = {}  # module cache per shield_id
        self._file_mtimes: dict[str, float] = {}  # path → mtime for auto-reload
        self.reload()

    def reload(self) -> None:
        self._shields = load_shields(self.shields_dirs)
        self._logic_cache.clear()
        self._snapshot_mtimes()
        logger.info("Shields loaded: %s", list(self._shields.keys()))

    def _snapshot_mtimes(self) -> None:
        """Record modification times of all shield files for change detection."""
        from pathlib import Path
        mtimes: dict[str, float] = {}
        for base_dir in self.shields_dirs:
            base = Path(base_dir)
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if f.is_file() and f.suffix in (".yaml", ".yml", ".py"):
                    mtimes[str(f)] = f.stat().st_mtime
        self._file_mtimes = mtimes

    def _check_for_changes(self) -> bool:
        """Return True if any shield file has been modified since last load."""
        from pathlib import Path
        for base_dir in self.shields_dirs:
            base = Path(base_dir)
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if f.is_file() and f.suffix in (".yaml", ".yml", ".py"):
                    path_str = str(f)
                    current_mtime = f.stat().st_mtime
                    if path_str not in self._file_mtimes:
                        return True  # new file
                    if current_mtime != self._file_mtimes[path_str]:
                        return True  # modified file
        return False

    @property
    def shields(self) -> dict[str, ShieldDefinition]:
        return self._shields

    async def scan(
        self,
        context: ScanContext,
        enabled_shield_ids: list[str] | None = None,
        shield_overrides: dict[str, dict] | None = None,
    ) -> ScanSummary:
        """
        Run all enabled shields against the context.

        Args:
            context: The normalized request content to scan.
            enabled_shield_ids: If set, only run these shields. None = run all.
            shield_overrides: Per-shield param overrides keyed by shield_id.
        """
        # Auto-reload shields if any files changed on disk
        if self._check_for_changes():
            logger.info("Shield files changed on disk — auto-reloading")
            self.reload()

        results: list[ShieldResult] = []
        all_findings: list[Finding] = []
        modified_body = dict(context.raw_body)  # copy for potential sanitization
        any_blocked = False
        any_sanitized = False
        any_warned = False

        for shield_id, shield in self._shields.items():
            # Skip globally disabled shields
            if not shield.enabled:
                continue

            # Skip if not in phase
            if context.phase not in (shield.phase, "both") and shield.phase != "both":
                if context.phase != shield.phase:
                    continue

            # Skip if not enabled
            if enabled_shield_ids is not None and shield_id not in enabled_shield_ids:
                continue

            # Merge params: shield defaults ← org overrides
            merged_params = dict(shield.params)
            if shield_overrides and shield_id in shield_overrides:
                merged_params.update(shield_overrides[shield_id])
            context.params = merged_params
            context.pattern_findings = []

            result = await self._run_shield(shield, context)
            results.append(result)

            if result.triggered:
                all_findings.extend(result.findings)
                action = result.effective_action
                if action == "block":
                    any_blocked = True
                elif action == "sanitize":
                    any_sanitized = True
                    _apply_sanitization(modified_body, result)
                elif action == "warn":
                    any_warned = True

        # ── Run LLM shields (DB-based) ────────────────────────────────────
        llm_results = await self._run_llm_shields(context)
        for result in llm_results:
            results.append(result)
            if result.triggered:
                all_findings.extend(result.findings)
                action = result.effective_action
                if action == "block":
                    any_blocked = True
                elif action == "warn":
                    any_warned = True

        if any_blocked:
            outcome = "blocked"
        elif any_sanitized:
            outcome = "sanitized"
        elif any_warned:
            outcome = "warned"
        else:
            outcome = "clean"

        return ScanSummary(
            request_id=context.request_id,
            outcome=outcome,
            results=results,
            all_findings=all_findings,
            modified_body=modified_body if outcome == "sanitized" else None,
        )

    async def _run_shield(self, shield: ShieldDefinition, context: ScanContext) -> ShieldResult:
        findings: list[Finding] = []

        # 1. Pattern matching
        for pattern in shield.patterns:
            pattern_findings = _match_pattern(pattern, context, shield.id)
            findings.extend(pattern_findings)
            context.pattern_findings.extend(pattern_findings)

        # 2. Logic module (if any)
        if shield.logic_module:
            try:
                logic = self._get_logic_module(shield)
                if hasattr(logic, "scan"):
                    logic_result: ShieldResult = await logic.scan(context)
                    findings.extend(logic_result.findings)
            except Exception as exc:
                logger.exception("Error in logic module for shield %s: %s", shield.id, exc)

        # 3. Enforce shield-level default_action.
        #    default_action acts as both floor AND ceiling:
        #    - If a finding's action is below default_action, elevate it.
        #    - If a finding's action is above default_action, cap it.
        #    This means changing default_action to "warn" ensures nothing blocks.
        shield_action_rank = ACTION_RANK.get(shield.default_action, 0)
        for f in findings:
            finding_rank = ACTION_RANK.get(f.action, 0)
            if finding_rank != shield_action_rank:
                f.action = shield.default_action

        triggered = len(findings) > 0
        effective_action = resolve_effective_action(findings) if triggered else None

        return ShieldResult(
            shield_id=shield.id,
            triggered=triggered,
            findings=findings,
            effective_action=effective_action,
        )

    def _get_logic_module(self, shield: ShieldDefinition) -> Any:
        if shield.id not in self._logic_cache:
            assert shield.logic_module is not None
            self._logic_cache[shield.id] = import_logic_module(shield.logic_module)
        return self._logic_cache[shield.id]

    async def _run_llm_shields(self, context: ScanContext) -> list[ShieldResult]:
        """Run all enabled LLM shields from the database."""
        try:
            from sqlalchemy import select as sa_select
            from aigate.db.engine import async_session_factory
            from aigate.db.models.llm_shield import LlmShield
            from aigate.db.models.setting import Setting
            from aigate.shields.llm_evaluator import evaluate

            async with async_session_factory() as session:
                # Get shield LLM key
                key_row = await session.get(Setting, "shield_llm_key")
                api_key = key_row.value if key_row else ""
                if not api_key:
                    return []

                # Get enabled LLM shields
                result = await session.execute(
                    sa_select(LlmShield).where(LlmShield.enabled == True)  # noqa: E712
                )
                shields = result.scalars().all()

            if not shields:
                return []

            # Extract user text from context
            user_text = ""
            for msg in context.latest_turn:
                content = msg.get("content", "")
                user_text += (_extract_text(content) + " ")
            user_text = user_text.strip()

            if not user_text:
                return []

            results: list[ShieldResult] = []
            for shield in shields:
                try:
                    res = await evaluate(
                        user_text=user_text,
                        system_prompt=shield.system_prompt,
                        model=shield.model,
                        provider=shield.provider,
                        api_key=api_key,
                        shield_id=shield.id,
                        default_action=shield.default_action,
                        severity=shield.severity,
                    )
                    results.append(res)
                except Exception as exc:
                    logger.error("LLM shield %s failed: %s", shield.id, exc)
            return results
        except Exception as exc:
            logger.error("Error running LLM shields: %s", exc)
            return []


def _match_pattern(
    pattern: PatternDefinition, context: ScanContext, shield_id: str
) -> list[Finding]:
    findings: list[Finding] = []

    if "messages" in _get_applicable_targets(pattern):
        # By default only scan the latest turn — previous messages were
        # already scanned on earlier requests.  Set scan_all_messages=true
        # in shield params to override.
        scan_all = context.params.get("scan_all_messages", False)
        if scan_all:
            depth = context.params.get("scan_depth_messages", 50)
            messages_to_scan = context.messages[-depth:] if depth else context.messages
        else:
            messages_to_scan = context.latest_turn

        for i, msg in enumerate(messages_to_scan):
            # Role filter
            if pattern.role and msg.get("role") != pattern.role:
                continue

            text = _extract_text(msg.get("content", ""))
            if not text:
                continue

            matched = _check_text(pattern, text)
            if matched:
                findings.append(Finding(
                    pattern_id=pattern.id,
                    message_index=i,
                    matched_text=matched[:200],
                    severity=pattern.severity,
                    action=pattern.action,
                    replacement=pattern.replacement,
                    shield_id=shield_id,
                ))

    if "system_prompt" in _get_applicable_targets(pattern) and context.system_prompt:
        matched = _check_text(pattern, context.system_prompt)
        if matched:
            findings.append(Finding(
                pattern_id=pattern.id,
                message_index=None,
                matched_text=matched[:200],
                severity=pattern.severity,
                action=pattern.action,
                replacement=pattern.replacement,
                shield_id=shield_id,
            ))

    if "tool_results" in _get_applicable_targets(pattern):
        for j, tr in enumerate(context.tool_results):
            text = _extract_text(tr.get("content", ""))
            matched = _check_text(pattern, text)
            if matched:
                findings.append(Finding(
                    pattern_id=pattern.id,
                    message_index=j,
                    matched_text=matched[:200],
                    severity=pattern.severity,
                    action=pattern.action,
                    replacement=pattern.replacement,
                    shield_id=shield_id,
                    details={"source": "tool_result"},
                ))

    return findings


def _get_applicable_targets(pattern: PatternDefinition) -> list[str]:
    """Determine which targets this pattern applies to based on its field."""
    if pattern.field == "all":
        return ["messages", "system_prompt", "tool_results"]
    return ["messages", "system_prompt", "tool_results"]  # default: scan all


def _check_text(pattern: PatternDefinition, text: str) -> str:
    """Return the matched snippet if pattern fires, else empty string."""
    if pattern.type == "regex" and pattern.pattern:
        try:
            m = re.search(pattern.pattern, text)
            if m:
                return m.group(0)
        except re.error as e:
            logger.warning("Invalid regex in pattern %s: %s", pattern.id, e)

    elif pattern.type == "keyword":
        text_lower = text.lower()
        for kw in pattern.keywords:
            if kw.lower() in text_lower:
                return kw

    return ""


def _apply_sanitization(body: dict, result: ShieldResult) -> None:
    """Apply sanitize replacements to the request body (in-place)."""
    for finding in result.findings:
        if finding.action != "sanitize" or not finding.replacement:
            continue
        if "messages" in body:
            for msg in body["messages"]:
                content = msg.get("content")
                if isinstance(content, str):
                    msg["content"] = content.replace(finding.matched_text, finding.replacement)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            block["text"] = block["text"].replace(
                                finding.matched_text, finding.replacement
                            )
