from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, delete

from aigate.db.engine import async_session_factory
from aigate.db.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: str
    timestamp: str
    org_id: str
    provider: str
    model: str
    endpoint: str
    request_id: str
    # W3C Trace Context fields
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    traceparent: str | None = None  # W3C traceparent header value
    scan_outcome: str
    skills_triggered: list
    input_tokens: int | None
    output_tokens: int | None
    proxy_latency_ms: int | None
    upstream_latency_ms: int | None
    duration_us: int | None = None
    scan_duration_us: int | None = None
    message_preview: str | None = None
    http_status: int
    request_body: dict | None = None
    response_body: dict | None = None


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    org_id: str | None = None,
    outcome: str | None = None,
    provider: str | None = None,
    trace_id: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    async with async_session_factory() as session:
        q = select(AuditLog).order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
        if org_id:
            q = q.where(AuditLog.org_id == uuid.UUID(org_id))
        if outcome:
            q = q.where(AuditLog.scan_outcome == outcome)
        if provider:
            q = q.where(AuditLog.provider == provider)
        if trace_id:
            q = q.where(AuditLog.trace_id == trace_id)
        result = await session.execute(q)
        logs = result.scalars().all()
    return [_to_response(log) for log in logs]


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(log_id: str):
    async with async_session_factory() as session:
        log = await session.get(AuditLog, uuid.UUID(log_id))
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return _to_response(log)


@router.delete("")
async def clear_audit_logs():
    """Delete all audit log entries."""
    async with async_session_factory() as session:
        await session.execute(delete(AuditLog))
        await session.commit()
    return {"status": "ok", "message": "All audit logs cleared"}


def _build_traceparent(trace_id: str | None, span_id: str | None) -> str | None:
    """Build W3C traceparent header: version-trace_id-span_id-flags"""
    if trace_id and span_id:
        return f"00-{trace_id}-{span_id}-01"
    return None


def _to_response(log: AuditLog) -> AuditLogResponse:
    trace_id = getattr(log, "trace_id", None)
    span_id = getattr(log, "span_id", None)
    return AuditLogResponse(
        id=str(log.id),
        timestamp=log.timestamp.isoformat(),
        org_id=str(log.org_id),
        provider=log.provider,
        model=log.model,
        endpoint=log.endpoint,
        request_id=log.request_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=getattr(log, "parent_span_id", None),
        traceparent=_build_traceparent(trace_id, span_id),
        scan_outcome=log.scan_outcome,
        skills_triggered=log.skills_triggered or [],
        input_tokens=log.input_tokens,
        output_tokens=log.output_tokens,
        proxy_latency_ms=log.proxy_latency_ms,
        upstream_latency_ms=log.upstream_latency_ms,
        duration_us=getattr(log, "duration_us", None),
        scan_duration_us=getattr(log, "scan_duration_us", None),
        message_preview=getattr(log, "message_preview", None),
        http_status=log.http_status,
        request_body=getattr(log, "request_body_redacted", None),
        response_body=getattr(log, "response_body_redacted", None),
    )
