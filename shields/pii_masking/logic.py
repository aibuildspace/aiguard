"""
PII masking logic module.

All PII detection is handled here (no patterns in shield.yaml) so each
category can be toggled on/off via the ``mask_*`` params.  These params
are set from the Settings → PII Masking UI and merged in as shield
overrides by the proxy router.

Every finding uses action="sanitize" with a typed replacement placeholder
so the runner's _apply_sanitization() rewrites the request body before it
reaches the upstream LLM.
"""
from __future__ import annotations

import re
from typing import Any


# ── Compiled regex patterns ──────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
)

_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(\+?1[-.\s]?)?"
    r"(\(?\d{3}\)?[-.\s]?)"
    r"(\d{3}[-.\s]?)"
    r"(\d{4})"
    r"(?!\d)"
)

_SSN_RE = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"
)

_CREDIT_CARD_RE = re.compile(
    r"\b(?:4[0-9]{3}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}"
    r"|5[1-5][0-9]{2}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}"
    r"|3[47][0-9]{2}[-\s]?[0-9]{6}[-\s]?[0-9]{5}"
    r"|6(?:011|5[0-9]{2})[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4})\b"
)

_API_KEY_RE = re.compile(
    r"(?i)(api[_\-]?key|secret[_\-]?key|access[_\-]?token)"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{20,})"
)

_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

_PRIVATE_KEY_MARKERS = [
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
]

_IBAN_RE = re.compile(
    r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"
)

_PASSPORT_RE = re.compile(r"\b[A-Z]{1,2}[0-9]{6,9}\b")

_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

_DOB_RE = re.compile(
    r"\b(?:"
    r"\d{4}[-/]\d{2}[-/]\d{2}"
    r"|\d{2}[-/]\d{2}[-/]\d{4}"
    r"|\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{4}"
    r")\b",
    re.IGNORECASE,
)

# ── Toggle → (regex, pattern_id, severity, replacement) ─────────────────────
# Each entry: (param_key, regex_or_None, pattern_id, severity, replacement, keywords_or_None)
_DETECTORS: list[tuple[str, re.Pattern | None, str, str, str, list[str] | None]] = [
    ("mask_emails",       _EMAIL_RE,       "email_address",  "medium", "[MASKED-EMAIL]",       None),
    ("mask_ssn",          _SSN_RE,         "ssn_us",         "high",   "[MASKED-SSN]",         None),
    ("mask_credit_cards", _CREDIT_CARD_RE, "credit_card",    "high",   "[MASKED-CC]",          None),
    ("mask_api_keys",     _API_KEY_RE,     "api_key",        "high",   "[MASKED-API-KEY]",     None),
    ("mask_aws_keys",     _AWS_KEY_RE,     "aws_access_key", "high",   "[MASKED-AWS-KEY]",     None),
    ("mask_iban",         _IBAN_RE,        "iban",           "high",   "[MASKED-IBAN]",        None),
    ("mask_passport",     _PASSPORT_RE,    "passport",       "medium", "[MASKED-PASSPORT]",    None),
    ("mask_ip_addresses", _IPV4_RE,        "ip_address",     "low",    "[MASKED-IP]",          None),
    ("mask_private_keys", None,            "private_key",    "high",   "[MASKED-PRIVATE-KEY]", _PRIVATE_KEY_MARKERS),
]


async def scan(context: Any) -> Any:
    from aigate.shields.models import Finding, ShieldResult, resolve_effective_action

    findings: list[Finding] = []

    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        content = _extract_text(msg.get("content", ""))
        if not content:
            continue

        # Run all regex/keyword detectors whose toggle is enabled
        for param_key, regex, pattern_id, severity, replacement, keywords in _DETECTORS:
            if not context.params.get(param_key, True):
                continue

            if regex is not None:
                for m in regex.finditer(content):
                    matched = m.group(0)
                    # Phone-specific: filter short false positives
                    if pattern_id == "phone_number":
                        digits = re.sub(r"\D", "", matched)
                        if len(digits) < 10:
                            continue
                    findings.append(Finding(
                        pattern_id=pattern_id,
                        message_index=i,
                        matched_text=matched[:200],
                        severity=severity,
                        action="sanitize",
                        replacement=replacement,
                        shield_id="pii_masking",
                    ))
            elif keywords:
                lower_content = content.lower()
                for kw in keywords:
                    if kw.lower() in lower_content:
                        findings.append(Finding(
                            pattern_id=pattern_id,
                            message_index=i,
                            matched_text=kw[:200],
                            severity=severity,
                            action="sanitize",
                            replacement=replacement,
                            shield_id="pii_masking",
                        ))

        # Phone numbers (separate because of digit-length filtering)
        if context.params.get("mask_phones", True):
            for m in _PHONE_RE.finditer(content):
                digits = re.sub(r"\D", "", m.group(0))
                if len(digits) >= 10:
                    findings.append(Finding(
                        pattern_id="phone_number",
                        message_index=i,
                        matched_text=m.group(0),
                        severity="medium",
                        action="sanitize",
                        replacement="[MASKED-PHONE]",
                        shield_id="pii_masking",
                    ))

        # Date of birth (opt-in)
        if context.params.get("mask_dates_of_birth", False):
            for m in _DOB_RE.finditer(content):
                findings.append(Finding(
                    pattern_id="date_of_birth",
                    message_index=i,
                    matched_text=m.group(0),
                    severity="medium",
                    action="sanitize",
                    replacement="[MASKED-DOB]",
                    shield_id="pii_masking",
                ))

    # NER-based name masking (opt-in, requires spaCy)
    if context.params.get("mask_names", False):
        try:
            ner_findings = await _run_ner_masking(context)
            findings.extend(ner_findings)
        except ImportError:
            pass

    triggered = len(findings) > 0
    return ShieldResult(
        shield_id="pii_masking",
        triggered=triggered,
        findings=findings,
        effective_action=resolve_effective_action(findings) if triggered else None,
    )


async def _run_ner_masking(context: Any) -> list:
    """Use spaCy NER to detect and mask person names."""
    import spacy
    from aigate.shields.models import Finding

    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        return []

    findings: list[Finding] = []

    scan_all = context.params.get("scan_all_messages", False)
    messages_to_scan = context.messages if scan_all else context.latest_turn

    for i, msg in enumerate(messages_to_scan):
        content = _extract_text(msg.get("content", ""))
        if not content or len(content) > 5000:
            continue

        doc = nlp(content)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                findings.append(Finding(
                    pattern_id="ner_person",
                    message_index=i,
                    matched_text=ent.text,
                    severity="medium",
                    action="sanitize",
                    replacement="[MASKED-NAME]",
                    shield_id="pii_masking",
                    details={"entity_type": ent.label_},
                ))

    return findings


def _extract_text(content: Any) -> str:
    """Normalize message content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content) if content else ""
