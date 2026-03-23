"""
LLM Shield evaluator — calls an LLM to evaluate user content.

This module is used by the shield runner when a shield has type="llm".
It sends the user's message to an evaluator LLM with a custom system prompt
and parses the structured response to determine pass/fail.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from aiguard.shields.models import Finding, ShieldResult, _extract_text

logger = logging.getLogger(__name__)

# Expected JSON response schema from the evaluator LLM
_EVALUATOR_SYSTEM_SUFFIX = """

You MUST respond with ONLY a JSON object (no markdown, no explanation) in this exact format:
{"pass": true} if the content is acceptable, or
{"pass": false, "reason": "<brief explanation>"} if the content should be flagged.
"""


async def evaluate(
    user_text: str,
    system_prompt: str,
    *,
    model: str = "gpt-4o-mini",
    provider: str = "openai",
    api_key: str = "",
    shield_id: str = "llm_shield",
    default_action: str = "warn",
    severity: str = "medium",
) -> ShieldResult:
    """Call an LLM to evaluate user content against a custom policy.

    Args:
        user_text: The user message content to evaluate.
        system_prompt: The custom system prompt defining the evaluation criteria.
        model: The LLM model to use for evaluation.
        provider: "openai" or "anthropic".
        api_key: The API key for the evaluator LLM.
        shield_id: Shield identifier for findings.
        default_action: Action to take when content is flagged.
        severity: Severity level for findings.

    Returns:
        ShieldResult with findings if content was flagged.
    """
    if not api_key:
        logger.warning("LLM shield %s: no API key configured, skipping", shield_id)
        return ShieldResult(shield_id=shield_id, triggered=False)

    if not user_text.strip():
        return ShieldResult(shield_id=shield_id, triggered=False)

    full_system = system_prompt.strip() + _EVALUATOR_SYSTEM_SUFFIX

    try:
        if provider == "anthropic":
            result = await _call_anthropic(api_key, model, full_system, user_text)
        else:
            result = await _call_openai(api_key, model, full_system, user_text)
    except Exception as exc:
        logger.error("LLM shield %s evaluation failed: %s", shield_id, exc)
        # On error, don't block — just pass through
        return ShieldResult(shield_id=shield_id, triggered=False)

    if result.get("pass", True):
        return ShieldResult(shield_id=shield_id, triggered=False)

    reason = result.get("reason", "Content flagged by LLM shield")
    finding = Finding(
        pattern_id="llm_evaluation",
        message_index=0,
        matched_text=reason[:200],
        severity=severity,
        action=default_action,
        shield_id=shield_id,
        details={"reason": reason, "model": model},
    )
    return ShieldResult(
        shield_id=shield_id,
        triggered=True,
        findings=[finding],
        effective_action=default_action,
    )


async def _call_openai(api_key: str, model: str, system: str, user_text: str) -> dict:
    """Call OpenAI Chat Completions API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0,
                "max_tokens": 150,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return _parse_json_response(content)


async def _call_anthropic(api_key: str, model: str, system: str, user_text: str) -> dict:
    """Call Anthropic Messages API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": [{"role": "user", "content": user_text}],
                "max_tokens": 150,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"].strip()
        return _parse_json_response(content)


def _parse_json_response(content: str) -> dict:
    """Parse the evaluator LLM's JSON response, handling common issues."""
    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
        # If we can't parse, assume pass
        logger.warning("Could not parse LLM shield response: %s", content[:200])
        return {"pass": True}
