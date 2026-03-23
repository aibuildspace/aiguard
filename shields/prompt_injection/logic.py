"""
Advanced prompt injection detection logic.
Handles obfuscated and encoded injection attempts that regex patterns miss.
"""
from __future__ import annotations

import base64
import re
from typing import Any


async def scan(context: Any) -> Any:
    """
    context: ScanContext — messages, system_prompt, tool_results, params, pattern_findings
    Returns: SkillResult
    """
    from aiguard.shields.models import Finding, ShieldResult

    findings = []

    _INJECTION_KEYWORDS = [
        "ignore", "jailbreak", "system:", "[inst]", "disregard",
        "bypass", "override", "you are now", "act as", "new instructions",
    ]

    # Only scan the latest turn — previous messages were already scanned
    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        if msg.get("role") != "user":
            continue

        content = _extract_text(msg.get("content", ""))
        if not content:
            continue

        # Check for base64-encoded injection
        b64_chunks = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", content)
        for chunk in b64_chunks:
            try:
                decoded = base64.b64decode(chunk + "==").decode("utf-8", errors="ignore")
                decoded_lower = decoded.lower()
                if any(kw in decoded_lower for kw in _INJECTION_KEYWORDS):
                    findings.append(Finding(
                        pattern_id="encoded_injection_base64",
                        message_index=i,
                        matched_text=chunk[:80] + "...",
                        severity="high",
                        action="block",
                        shield_id="prompt_injection",
                        details={"decoded_preview": decoded[:150]},
                    ))
                    break
            except Exception:
                pass

        # Check for unicode lookalike characters used to evade keyword matching
        # e.g. "ｉｇｎｏｒｅ" (fullwidth) instead of "ignore"
        normalized = content.encode("ascii", errors="ignore").decode("ascii").lower()
        fullwidth_decoded = "".join(
            chr(ord(c) - 0xFF00 + 0x20) if 0xFF01 <= ord(c) <= 0xFF5E else c
            for c in content
        ).lower()
        if any(kw in fullwidth_decoded for kw in _INJECTION_KEYWORDS) and \
                not any(kw in normalized for kw in _INJECTION_KEYWORDS):
            findings.append(Finding(
                pattern_id="unicode_obfuscation",
                message_index=i,
                matched_text=content[:100],
                severity="high",
                action="block",
                shield_id="prompt_injection",
                details={"technique": "fullwidth_unicode"},
            ))

    triggered = len(findings) > 0
    return ShieldResult(
        shield_id="prompt_injection",
        triggered=triggered,
        findings=findings,
        effective_action="block" if triggered else None,
    )


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content) if content else ""
