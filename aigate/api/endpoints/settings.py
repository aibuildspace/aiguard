from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from aigate.db.engine import async_session_factory
from aigate.db.models.setting import Setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Keys we persist
_GRAFANA_KEYS = [
    "grafana_enabled",
    "grafana_otlp_endpoint",
    "grafana_otlp_headers",
    "grafana_service_name",
    "grafana_trace_playground",
    "grafana_trace_claude_code",
    "grafana_trace_openclaw",
]

_SHIELD_LLM_KEYS = [
    "shield_llm_key",
    "shield_llm_provider",
]

_BOOLEAN_KEYS = {
    "grafana_enabled",
    "grafana_trace_playground",
    "grafana_trace_claude_code",
    "grafana_trace_openclaw",
}

_SECRET_KEYS = {"shield_llm_key"}


class SettingsPayload(BaseModel):
    grafana_enabled: bool = False
    grafana_otlp_endpoint: str = ""
    grafana_otlp_headers: str = ""
    grafana_service_name: str = "aigate"
    grafana_trace_playground: bool = True
    grafana_trace_claude_code: bool = True
    grafana_trace_openclaw: bool = True


class TestGrafanaPayload(BaseModel):
    grafana_otlp_endpoint: str
    grafana_otlp_headers: str = ""


@router.get("")
async def get_settings():
    """Return all persisted settings as a flat dict."""
    async with async_session_factory() as session:
        result = await session.execute(select(Setting))
        rows = result.scalars().all()
    out: dict[str, str | bool] = {}
    for row in rows:
        # Convert "true"/"false" strings back to bool for known boolean keys
        if row.key in _BOOLEAN_KEYS:
            out[row.key] = row.value == "true"
        elif row.key in _SECRET_KEYS:
            # Mask secrets — only return whether it's set
            out[row.key] = "••••••••" if row.value else ""
            out[row.key + "_set"] = bool(row.value)
        else:
            out[row.key] = row.value
    return out


@router.post("")
async def save_settings(payload: SettingsPayload):
    """Upsert settings from the payload."""
    data = payload.model_dump()
    async with async_session_factory() as session:
        for key in _GRAFANA_KEYS:
            val = str(data.get(key, ""))
            # Normalise booleans
            if isinstance(data.get(key), bool):
                val = "true" if data[key] else "false"
            existing = await session.get(Setting, key)
            if existing:
                existing.value = val
            else:
                session.add(Setting(key=key, value=val))
        await session.commit()
    return {"status": "ok"}


class ShieldLlmPayload(BaseModel):
    shield_llm_key: str = ""
    shield_llm_provider: str = "openai"


@router.post("/shield-llm-key")
async def save_shield_llm_key(payload: ShieldLlmPayload):
    """Save the API key used by LLM shields for content evaluation."""
    async with async_session_factory() as session:
        for key in _SHIELD_LLM_KEYS:
            val = getattr(payload, key, "")
            existing = await session.get(Setting, key)
            if existing:
                existing.value = val
            else:
                session.add(Setting(key=key, value=val))
        await session.commit()
    logger.info("Shield LLM key %s", "updated" if payload.shield_llm_key else "cleared")
    return {"ok": True}


@router.delete("/shield-llm-key")
async def delete_shield_llm_key():
    """Remove the shield LLM API key."""
    async with async_session_factory() as session:
        for key in _SHIELD_LLM_KEYS:
            existing = await session.get(Setting, key)
            if existing:
                existing.value = ""
        await session.commit()
    logger.info("Shield LLM key removed")
    return {"ok": True}


@router.post("/test-grafana")
async def test_grafana_connection(payload: TestGrafanaPayload):
    """Send a minimal OTLP health-check request to validate connectivity."""
    endpoint = payload.grafana_otlp_endpoint.rstrip("/")
    if not endpoint:
        return {"ok": False, "detail": "Endpoint URL is required"}

    # OTLP/HTTP traces endpoint
    url = f"{endpoint}/v1/traces"
    headers = {"Content-Type": "application/json"}
    if payload.grafana_otlp_headers:
        headers["Authorization"] = payload.grafana_otlp_headers

    # Send an empty but valid OTLP ExportTraceServiceRequest
    body = {"resourceSpans": []}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code < 400:
            return {"ok": True, "detail": f"Connected ({resp.status_code})"}
        elif resp.status_code == 404:
            hint = ""
            if "tempo-prod" in endpoint or endpoint.rstrip("/").endswith("/tempo"):
                hint = " — This looks like a Tempo query URL. Use the OTLP gateway instead: https://otlp-gateway-{region}.grafana.net/otlp"
            return {"ok": False, "detail": f"HTTP 404: {resp.text[:120]}{hint}"}
        elif resp.status_code == 401 or resp.status_code == 403:
            text = resp.text[:200]
            if "invalid scope" in text.lower():
                return {"ok": False, "detail": f"HTTP {resp.status_code}: Token lacks write permission. Create a new token via Access Policies with the traces:write scope."}
            return {"ok": False, "detail": f"HTTP {resp.status_code}: Authentication failed. Check your Instance ID and API token."}
        else:
            return {"ok": False, "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.ConnectError as e:
        return {"ok": False, "detail": f"Connection failed: {e}"}
    except Exception as e:
        logger.warning("Grafana test failed: %s", e)
        return {"ok": False, "detail": str(e)[:200]}
