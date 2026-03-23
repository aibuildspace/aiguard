from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Query
from sqlalchemy import select, func, desc

from aiguard.db.engine import async_session_factory
from aiguard.db.models.audit_log import AuditLog
from aiguard.db.models.org import Org
from aiguard.db.models.user import User
from aiguard.db.models.api_key import ApiKey

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard_stats(request: Request):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session_factory() as session:
        # Request counts today
        base = select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= today_start)
        requests_today = (await session.execute(base)).scalar() or 0
        blocked_today = (
            await session.execute(base.where(AuditLog.scan_outcome == "blocked"))
        ).scalar() or 0
        warned_today = (
            await session.execute(base.where(AuditLog.scan_outcome == "warned"))
        ).scalar() or 0

        # Entity counts
        active_orgs = (await session.execute(select(func.count()).select_from(Org))).scalar() or 0
        active_users = (
            await session.execute(
                select(func.count()).select_from(User).where(User.is_active == True)
            )
        ).scalar() or 0
        active_keys = (
            await session.execute(
                select(func.count()).select_from(ApiKey).where(ApiKey.is_active == True)
            )
        ).scalar() or 0

        # Token sums today
        token_result = await session.execute(
            select(
                func.coalesce(func.sum(AuditLog.input_tokens), 0),
                func.coalesce(func.sum(AuditLog.output_tokens), 0),
            ).where(AuditLog.timestamp >= today_start)
        )
        row = token_result.one()
        input_tokens_today = row[0]
        output_tokens_today = row[1]

        # Recent audit logs (last 200 for the heatmap grid)
        recent_q = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(200)
        recent_result = await session.execute(recent_q)
        recent_logs = recent_result.scalars().all()

    # Shields count from app state
    runner = getattr(request.app.state, "shield_runner", None)
    shields_loaded = len(runner.shields) if runner else 0

    return {
        "requests_today": requests_today,
        "blocked_today": blocked_today,
        "warned_today": warned_today,
        "shields_loaded": shields_loaded,
        "active_orgs": active_orgs,
        "active_users": active_users,
        "active_keys": active_keys,
        "input_tokens_today": input_tokens_today,
        "output_tokens_today": output_tokens_today,
        "recent_logs": [
            {
                "id": str(log.id),
                "timestamp": log.timestamp.isoformat(),
                "provider": log.provider,
                "model": log.model,
                "endpoint": log.endpoint,
                "request_id": log.request_id,
                "trace_id": getattr(log, "trace_id", None),
                "span_id": getattr(log, "span_id", None),
                "scan_outcome": log.scan_outcome,
                "skills_triggered": log.skills_triggered or [],
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "proxy_latency_ms": log.proxy_latency_ms,
                "upstream_latency_ms": log.upstream_latency_ms,
                "http_status": log.http_status,
                "message_preview": getattr(log, "message_preview", None),
                "duration_us": getattr(log, "duration_us", None),
                "scan_duration_us": getattr(log, "scan_duration_us", None),
            }
            for log in recent_logs
        ],
    }
