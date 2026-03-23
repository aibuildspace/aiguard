"""
PII detection logic module.
Extends pattern-based detection with optional NER (spaCy) when use_ner=true.
"""
from __future__ import annotations

import re
from typing import Any


# Phone number regex (international and US formats)
_PHONE_RE = re.compile(
    r"\b(\+?1[-.\s]?)?"
    r"(\(?\d{3}\)?[-.\s]?)"
    r"(\d{3}[-.\s]?)"
    r"(\d{4})"
    r"\b"
)

# Email addresses
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
)


async def scan(context: Any) -> Any:
    from aiguard.shields.models import Finding, ShieldResult

    findings = []
    log_only = context.params.get("log_emails", False)

    # Only scan the latest turn — previous messages were already scanned
    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        content = _extract_text(msg.get("content", ""))
        if not content:
            continue

        # Phone number detection
        for m in _PHONE_RE.finditer(content):
            phone = m.group(0)
            # Filter out likely false positives (e.g. version numbers, IDs < 10 digits)
            digits = re.sub(r"\D", "", phone)
            if len(digits) >= 10:
                findings.append(Finding(
                    pattern_id="phone_number",
                    message_index=i,
                    matched_text=phone,
                    severity="low",
                    action="log",
                    shield_id="pii_detection",
                ))

        # Email detection — log by default, not block
        for m in _EMAIL_RE.finditer(content):
            findings.append(Finding(
                pattern_id="email_address",
                message_index=i,
                matched_text=m.group(0),
                severity="low",
                action="log",
                shield_id="pii_detection",
            ))

        try:
            ner_findings = await _run_ner(context)
            findings.extend(ner_findings)
        except ImportError:
            pass

    triggered = len(findings) > 0
    from aiguard.shields.models import resolve_effective_action
    return ShieldResult(
        shield_id="pii_detection",
        triggered=triggered,
        findings=findings,
        effective_action=resolve_effective_action(findings) if triggered else None,
    )


async def _run_ner(context: Any) -> list:
    """Use spaCy NER for entity detection. Requires: pip install spacy && python -m spacy download en_core_web_sm"""
    import spacy
    from aiguard.shields.models import Finding

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        return []

    findings = []
    target_entities = set(context.params.get("ner_entities", ["PERSON", "ORG", "GPE"]))

    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        content = _extract_text(msg.get("content", ""))
        if not content or len(content) > 5000:
            continue
        doc = nlp(content)
        for ent in doc.ents:
            if ent.label_ in target_entities:
                findings.append(Finding(
                    pattern_id=f"ner_{ent.label_.lower()}",
                    message_index=i,
                    matched_text=ent.text,
                    severity="low",
                    action="log",
                    shield_id="pii_detection",
                    details={"entity_type": ent.label_},
                ))
    return findings


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
