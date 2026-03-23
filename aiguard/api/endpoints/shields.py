from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from aiguard.shields.loader import find_shield_file, read_shield, write_shield

router = APIRouter(prefix="/shields", tags=["shields"])


class ShieldResponse(BaseModel):
    id: str
    name: str
    version: str
    type: str
    description: str
    tags: list[str]
    phase: str
    default_action: str
    severity: str
    pattern_count: int
    has_logic_module: bool
    shield_dir: str
    enabled: bool


@router.get("", response_model=list[ShieldResponse])
async def list_shields(request: Request):
    runner = request.app.state.shield_runner
    return [_to_response(s) for s in runner.shields.values()]


@router.get("/{shield_id}", response_model=ShieldResponse)
async def get_shield(shield_id: str, request: Request):
    runner = request.app.state.shield_runner
    shield = runner.shields.get(shield_id)
    if not shield:
        raise HTTPException(status_code=404, detail=f"Shield '{shield_id}' not found")
    return _to_response(shield)


@router.post("/reload", status_code=200)
async def reload_shields(request: Request):
    runner = request.app.state.shield_runner
    runner.reload()
    return {"reloaded": len(runner.shields), "shield_ids": list(runner.shields.keys())}


class ShieldUpdate(BaseModel):
    default_action: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


_VALID_ACTIONS = {"block", "warn", "sanitize", "log", "pass"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


@router.patch("/{shield_id}", response_model=ShieldResponse)
async def update_shield(shield_id: str, body: ShieldUpdate, request: Request):
    """Update a shield's config → write shield.yaml → reload."""
    runner = request.app.state.shield_runner
    shield = runner.shields.get(shield_id)
    if not shield:
        raise HTTPException(status_code=404, detail=f"Shield '{shield_id}' not found")

    if body.default_action and body.default_action not in _VALID_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Invalid action: {body.default_action}")
    if body.severity and body.severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"Invalid severity: {body.severity}")

    shield_dir = Path(shield.shield_dir)
    shield_file = find_shield_file(shield_dir)
    if not shield_file:
        raise HTTPException(status_code=500, detail="No shield file on disk")

    data, description = read_shield(shield_file)

    changed = False
    if body.default_action and data.get("default_action") != body.default_action:
        data["default_action"] = body.default_action
        changed = True
    if body.severity and data.get("severity") != body.severity:
        data["severity"] = body.severity
        changed = True
    if body.description is not None and body.description != description:
        description = body.description
        changed = True
    if body.enabled is not None and data.get("enabled", True) != body.enabled:
        data["enabled"] = body.enabled
        changed = True

    if changed:
        write_shield(shield_dir, data, description)
        runner.reload()

    updated = runner.shields.get(shield_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Shield disappeared after reload")
    return _to_response(updated)


@router.post("/test/{shield_id}")
async def test_shield(shield_id: str, payload: dict, request: Request):
    """Test a shield against a provided message."""
    import uuid as _uuid
    from aiguard.shields.models import ScanContext
    from aiguard.proxy.providers.anthropic import AnthropicProvider

    runner = request.app.state.shield_runner
    shield = runner.shields.get(shield_id)
    if not shield:
        raise HTTPException(status_code=404, detail=f"Shield '{shield_id}' not found")

    provider = AnthropicProvider()
    content = provider.extract_content(payload)

    context = ScanContext(
        request_id=str(_uuid.uuid4()),
        org_id="test",
        user_id=None,
        provider="test",
        model=content.get("model", ""),
        phase="pre_request",
        messages=content.get("messages", []),
        system_prompt=content.get("system_prompt"),
        tool_results=content.get("tool_results", []),
        raw_body=payload,
    )

    result = await runner._run_shield(shield, context)
    return {
        "shield_id": shield_id,
        "triggered": result.triggered,
        "effective_action": result.effective_action,
        "findings": [
            {
                "pattern_id": f.pattern_id,
                "message_index": f.message_index,
                "matched_text": f.matched_text,
                "severity": f.severity,
                "action": f.action,
            }
            for f in result.findings
        ],
    }


def _to_response(shield) -> ShieldResponse:
    return ShieldResponse(
        id=shield.id,
        name=shield.name,
        version=shield.version,
        type=shield.type,
        description=shield.description,
        tags=shield.tags,
        phase=shield.phase,
        default_action=shield.default_action,
        severity=shield.severity,
        pattern_count=len(shield.patterns),
        has_logic_module=shield.logic_module is not None,
        shield_dir=shield.shield_dir,
        enabled=shield.enabled,
    )
