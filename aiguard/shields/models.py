from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


ActionType = Literal["block", "warn", "sanitize", "log", "pass"]
SeverityLevel = Literal["critical", "high", "medium", "low", "info"]
PhaseType = Literal["pre_request", "post_response", "both"]

# Severity ranking for resolving the highest-severity action
SEVERITY_RANK: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}

ACTION_RANK: dict[str, int] = {
    "block": 4,
    "sanitize": 3,
    "warn": 2,
    "log": 1,
    "pass": 0,
}


@dataclass
class PatternDefinition:
    id: str
    type: Literal["regex", "keyword"]
    field: Literal["content", "role", "all"]
    pattern: str = ""  # for regex
    keywords: list[str] = field(default_factory=list)  # for keyword
    role: str | None = None  # restrict to messages of this role
    severity: SeverityLevel = "medium"
    action: ActionType = "warn"
    replacement: str | None = None  # for sanitize action
    description: str = ""


@dataclass
class ShieldDefinition:
    id: str
    name: str
    version: str
    type: str  # pattern, logic, llm
    description: str
    author: str
    tags: list[str]
    targets: list[str]  # messages, tool_results, system_prompt, all_text
    phase: PhaseType
    default_action: ActionType
    severity: SeverityLevel
    patterns: list[PatternDefinition]
    logic_module: str | None  # path to logic.py relative to shield dir
    params: dict[str, Any]
    shield_dir: str  # absolute path to the shield directory
    enabled: bool = True  # global enable/disable toggle


@dataclass
class Finding:
    pattern_id: str
    message_index: int | None
    matched_text: str  # truncated snippet for logging
    severity: SeverityLevel
    action: ActionType
    replacement: str | None = None
    details: dict = field(default_factory=dict)
    shield_id: str = ""


@dataclass
class ShieldResult:
    shield_id: str
    triggered: bool
    findings: list[Finding] = field(default_factory=list)
    # Highest-priority action across all findings (or None if not triggered)
    effective_action: ActionType | None = None
    # Modified content after sanitize actions (None = no change)
    sanitized_content: str | None = None


@dataclass
class ScanContext:
    request_id: str
    org_id: str
    user_id: str | None
    provider: str
    model: str
    phase: PhaseType

    # Normalized content extracted from the request
    messages: list[dict]       # [{"role": "user", "content": "..."}]
    system_prompt: str | None
    tool_results: list[dict]
    raw_body: dict             # original parsed request body

    # Populated by pattern matching before logic modules run
    pattern_findings: list[Finding] = field(default_factory=list)

    # Merged params for the current shield (set by runner per shield)
    params: dict = field(default_factory=dict)

    @property
    def latest_turn(self) -> list[dict]:
        """Return only the last user message (the newest content in this request).

        In a multi-turn conversation the earlier messages were already
        scanned when they were first sent, so shields should focus on new
        content only.  We return just the final message if it's a user
        message, otherwise scan nothing (assistant/system trailing
        messages don't need scanning).
        """
        if not self.messages:
            return []

        last = self.messages[-1]
        if last.get("role") == "user":
            return [last]
        return []

    @property
    def all_user_text(self) -> str:
        """Convenience: all user-role message text concatenated."""
        parts = []
        for msg in self.messages:
            if msg.get("role") == "user":
                parts.append(_extract_text(msg.get("content", "")))
        return " ".join(parts)


@dataclass
class ScanSummary:
    request_id: str
    outcome: Literal["clean", "warned", "blocked", "sanitized"]
    results: list[ShieldResult]
    # Flat list of all findings across shields
    all_findings: list[Finding] = field(default_factory=list)
    # Modified body if any sanitize actions ran
    modified_body: dict | None = None


def _extract_text(content: Any) -> str:
    """Normalize message content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content) if content else ""


def resolve_effective_action(findings: list[Finding]) -> ActionType:
    """Return the highest-priority action across all findings."""
    if not findings:
        return "pass"
    return max(findings, key=lambda f: ACTION_RANK.get(f.action, 0)).action
