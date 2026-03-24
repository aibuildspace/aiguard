"""
Content policy shield — checks user-configured keyword blocklist.
Configure via org policy: shield_params.content_policy.blocked_keywords = ["word1", "word2"]
"""
from __future__ import annotations

from typing import Any


async def scan(context: Any) -> Any:
    from aigate.shields.models import Finding, ShieldResult

    blocked_keywords: list[str] = context.params.get("blocked_keywords", [])
    case_sensitive: bool = context.params.get("case_sensitive", False)

    if not blocked_keywords:
        return ShieldResult(shield_id="content_policy", triggered=False, findings=[])

    findings = []

    # Only scan the latest turn — previous messages were already scanned
    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        if msg.get("role") not in ("user", None):
            continue
        content = _extract_text(msg.get("content", ""))
        check_content = content if case_sensitive else content.lower()

        for kw in blocked_keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in check_content:
                findings.append(Finding(
                    pattern_id="blocked_keyword",
                    message_index=i,
                    matched_text=kw,
                    severity="medium",
                    action="block",
                    shield_id="content_policy",
                    details={"keyword": kw},
                ))

    triggered = len(findings) > 0
    return ShieldResult(
        shield_id="content_policy",
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
