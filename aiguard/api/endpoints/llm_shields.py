"""
API endpoints for user-created LLM shields.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from aiguard.db.engine import async_session_factory
from aiguard.db.models.llm_shield import LlmShield
from aiguard.db.models.setting import Setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-shields", tags=["llm-shields"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class LlmShieldCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    model: str = "gpt-4o-mini"
    provider: str = "openai"
    default_action: str = "warn"
    severity: str = "medium"
    enabled: bool = True


class LlmShieldUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    default_action: Optional[str] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None


class LlmShieldResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    model: str
    provider: str
    default_action: str
    severity: str
    enabled: bool


# ── Validation ────────────────────────────────────────────────────────────────

_VALID_ACTIONS = {"block", "warn", "log", "pass"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_PROVIDERS = {"openai", "anthropic"}


def _validate_shield(data: dict) -> None:
    if data.get("default_action") and data["default_action"] not in _VALID_ACTIONS:
        raise HTTPException(422, f"Invalid action: {data['default_action']}")
    if data.get("severity") and data["severity"] not in _VALID_SEVERITIES:
        raise HTTPException(422, f"Invalid severity: {data['severity']}")
    if data.get("provider") and data["provider"] not in _VALID_PROVIDERS:
        raise HTTPException(422, f"Invalid provider: {data['provider']}")


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[LlmShieldResponse])
async def list_llm_shields():
    async with async_session_factory() as session:
        result = await session.execute(select(LlmShield).order_by(LlmShield.name))
        return [_to_response(s) for s in result.scalars().all()]


@router.get("/{shield_id}", response_model=LlmShieldResponse)
async def get_llm_shield(shield_id: str):
    async with async_session_factory() as session:
        shield = await session.get(LlmShield, shield_id)
        if not shield:
            raise HTTPException(404, f"LLM shield '{shield_id}' not found")
        return _to_response(shield)


@router.post("", response_model=LlmShieldResponse, status_code=201)
async def create_llm_shield(body: LlmShieldCreate):
    _validate_shield(body.model_dump())

    if not body.name.strip():
        raise HTTPException(422, "Name is required")
    if not body.system_prompt.strip():
        raise HTTPException(422, "System prompt is required")

    shield_id = _slugify(body.name)

    async with async_session_factory() as session:
        # Check uniqueness
        existing = await session.get(LlmShield, shield_id)
        if existing:
            raise HTTPException(409, f"LLM shield with id '{shield_id}' already exists")

        shield = LlmShield(
            id=shield_id,
            name=body.name.strip(),
            description=body.description.strip(),
            system_prompt=body.system_prompt.strip(),
            model=body.model,
            provider=body.provider,
            default_action=body.default_action,
            severity=body.severity,
            enabled=body.enabled,
        )
        session.add(shield)
        await session.commit()
        await session.refresh(shield)
        logger.info("Created LLM shield: %s", shield.id)
        return _to_response(shield)


@router.patch("/{shield_id}", response_model=LlmShieldResponse)
async def update_llm_shield(shield_id: str, body: LlmShieldUpdate):
    updates = body.model_dump(exclude_unset=True)
    _validate_shield(updates)

    async with async_session_factory() as session:
        shield = await session.get(LlmShield, shield_id)
        if not shield:
            raise HTTPException(404, f"LLM shield '{shield_id}' not found")

        for key, val in updates.items():
            setattr(shield, key, val)
        await session.commit()
        await session.refresh(shield)
        logger.info("Updated LLM shield: %s", shield.id)
        return _to_response(shield)


@router.delete("/{shield_id}")
async def delete_llm_shield(shield_id: str):
    async with async_session_factory() as session:
        shield = await session.get(LlmShield, shield_id)
        if not shield:
            raise HTTPException(404, f"LLM shield '{shield_id}' not found")
        await session.delete(shield)
        await session.commit()
        logger.info("Deleted LLM shield: %s", shield_id)
        return {"ok": True}


@router.post("/test/{shield_id}")
async def test_llm_shield(shield_id: str, payload: dict):
    """Test an LLM shield against provided content."""
    from aiguard.shields.llm_evaluator import evaluate

    async with async_session_factory() as session:
        shield = await session.get(LlmShield, shield_id)
        if not shield:
            raise HTTPException(404, f"LLM shield '{shield_id}' not found")

        # Get shield LLM key from settings
        api_key = await _get_shield_llm_key(session)
        if not api_key:
            raise HTTPException(400, "No Shield LLM Key configured. Add one in Settings.")

    # Extract user text from payload
    messages = payload.get("messages", [])
    user_text = ""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            user_text += (content if isinstance(content, str) else str(content)) + " "
    user_text = user_text.strip()

    if not user_text:
        raise HTTPException(422, "No user message content provided")

    result = await evaluate(
        user_text=user_text,
        system_prompt=shield.system_prompt,
        model=shield.model,
        provider=shield.provider,
        api_key=api_key,
        shield_id=shield.id,
        default_action=shield.default_action,
        severity=shield.severity,
    )

    return {
        "shield_id": shield.id,
        "triggered": result.triggered,
        "effective_action": result.effective_action,
        "findings": [
            {
                "pattern_id": f.pattern_id,
                "message_index": f.message_index,
                "matched_text": f.matched_text,
                "severity": f.severity,
                "action": f.action,
                "details": f.details,
            }
            for f in result.findings
        ],
    }


@router.post("/seed-defaults")
async def seed_default_shields():
    """Create a set of useful default LLM shields if they don't exist."""
    defaults = _get_default_shields()
    created = []
    async with async_session_factory() as session:
        for d in defaults:
            existing = await session.get(LlmShield, d["id"])
            if existing:
                continue
            shield = LlmShield(**d)
            session.add(shield)
            created.append(d["id"])
        await session.commit()
    return {"created": created, "total_defaults": len(defaults)}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_shield_llm_key(session) -> str:
    """Retrieve the shield LLM API key from settings."""
    row = await session.get(Setting, "shield_llm_key")
    return row.value if row else ""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    slug = slug.strip("_")
    return slug[:60] or uuid.uuid4().hex[:12]


def _to_response(shield: LlmShield) -> LlmShieldResponse:
    return LlmShieldResponse(
        id=shield.id,
        name=shield.name,
        description=shield.description,
        system_prompt=shield.system_prompt,
        model=shield.model,
        provider=shield.provider,
        default_action=shield.default_action,
        severity=shield.severity,
        enabled=shield.enabled,
    )


def _get_default_shields() -> list[dict]:
    """Return a list of meaningful default LLM shields."""
    return [
        {
            "id": "topic_guardrail",
            "name": "Topic Guardrail",
            "description": "Ensures conversations stay on-topic and relevant to business use. Flags off-topic requests like creative writing, personal advice, or entertainment.",
            "system_prompt": (
                "You are a content policy evaluator. Your job is to determine whether the user's message "
                "is appropriate for a professional/business AI assistant.\n\n"
                "The message should be FLAGGED (pass: false) if it:\n"
                "- Asks for creative writing, fiction, poetry, or storytelling\n"
                "- Requests personal relationship or dating advice\n"
                "- Asks for entertainment content (jokes, games, trivia)\n"
                "- Requests content unrelated to work, productivity, coding, analysis, or business\n\n"
                "The message should PASS (pass: true) if it:\n"
                "- Is related to coding, programming, or software development\n"
                "- Asks for data analysis, research, or business insights\n"
                "- Requests help with documents, emails, or professional communication\n"
                "- Is a general knowledge question relevant to work\n"
                "- Asks for technical explanations or learning"
            ),
            "model": "gpt-4o-mini",
            "provider": "openai",
            "default_action": "warn",
            "severity": "low",
            "enabled": False,
        },
        {
            "id": "tone_professionalism",
            "name": "Tone & Professionalism",
            "description": "Detects aggressive, abusive, or unprofessional language in user prompts. Helps maintain respectful communication standards.",
            "system_prompt": (
                "You are a tone and professionalism evaluator. Assess whether the user's message "
                "maintains professional and respectful communication standards.\n\n"
                "The message should be FLAGGED (pass: false) if it contains:\n"
                "- Profanity, slurs, or hate speech\n"
                "- Threatening, intimidating, or aggressive language\n"
                "- Harassment or bullying directed at individuals or groups\n"
                "- Extremely disrespectful or demeaning tone\n\n"
                "The message should PASS (pass: true) if it:\n"
                "- Uses professional or casual-but-respectful language\n"
                "- Expresses frustration without being abusive\n"
                "- Contains technical terms that might seem strong but are not aggressive\n"
                "- Is a normal business or technical conversation"
            ),
            "model": "gpt-4o-mini",
            "provider": "openai",
            "default_action": "block",
            "severity": "high",
            "enabled": False,
        },
        {
            "id": "sensitive_data_request",
            "name": "Sensitive Data Request",
            "description": "Detects when users ask the AI to generate or process sensitive data like passwords, credentials, financial info, or personal records.",
            "system_prompt": (
                "You are a data sensitivity evaluator. Determine whether the user is asking the AI "
                "to generate, create, or process sensitive information that could pose security risks.\n\n"
                "The message should be FLAGGED (pass: false) if it asks to:\n"
                "- Generate passwords, API keys, tokens, or credentials\n"
                "- Create fake identity documents, SSNs, or government IDs\n"
                "- Process or store credit card numbers or banking details\n"
                "- Generate medical records or health information\n"
                "- Create employee records with personal information\n\n"
                "The message should PASS (pass: true) if it:\n"
                "- Discusses security concepts in general terms\n"
                "- Asks how to implement password hashing or encryption\n"
                "- Requests code that handles sensitive data securely\n"
                "- Discusses data protection best practices\n"
                "- Asks about authentication/authorization patterns"
            ),
            "model": "gpt-4o-mini",
            "provider": "openai",
            "default_action": "warn",
            "severity": "medium",
            "enabled": False,
        },
    ]
