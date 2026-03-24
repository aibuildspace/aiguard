"""
Costing API: aggregates token usage from audit logs and computes estimated costs.

Pricing is approximate and based on published model pricing as of 2025.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, cast, Float

from aigate.db.engine import async_session_factory
from aigate.db.models.audit_log import AuditLog
from aigate.db.models.user import User

router = APIRouter(prefix="/costing", tags=["costing"])

# Approximate per-token pricing (USD per 1K tokens) — input / output
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini":      (0.00015, 0.0006),
    "gpt-4o":           (0.0025,  0.01),
    "gpt-4.1-mini":     (0.0004,  0.0016),
    "gpt-4.1":          (0.002,   0.008),
    "gpt-5.1-codex":    (0.002,   0.008),
    "o3-mini":          (0.0011,  0.0044),
    # Anthropic
    "claude-sonnet-4-20250514":   (0.003, 0.015),
    "claude-haiku-4-20250414":    (0.0008, 0.004),
    "claude-opus-4-20250514":     (0.015, 0.075),
}

DEFAULT_PRICING = (0.002, 0.008)  # fallback


class CostingSummary(BaseModel):
    period: str  # "today" | "7d" | "30d" | "all"
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    by_model: list[ModelCost]
    by_user: list[UserCost]
    by_day: list[DayCost]


class ModelCost(BaseModel):
    model: str
    provider: str
    requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class UserCost(BaseModel):
    user_id: str | None
    user_name: str | None
    user_email: str | None
    requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class DayCost(BaseModel):
    date: str
    requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens * in_price + output_tokens * out_price) / 1000.0


@router.get("/summary", response_model=CostingSummary)
async def costing_summary(
    period: str = Query(default="30d", pattern="^(today|7d|30d|all)$"),
):
    now = datetime.now(timezone.utc)
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        since = now - timedelta(days=7)
    elif period == "30d":
        since = now - timedelta(days=30)
    else:
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)

    async with async_session_factory() as session:
        base = select(AuditLog).where(AuditLog.timestamp >= since)
        result = await session.execute(base)
        logs = result.scalars().all()

        # Fetch user map for enrichment
        user_ids = {l.user_id for l in logs if l.user_id}
        user_map = {}
        if user_ids:
            users_result = await session.execute(
                select(User).where(User.id.in_(user_ids))
            )
            for u in users_result.scalars().all():
                user_map[u.id] = u

    # Aggregate by model
    model_agg: dict[str, dict] = {}
    user_agg: dict[str | None, dict] = {}
    day_agg: dict[str, dict] = {}
    total_in = 0
    total_out = 0
    total_cost = 0.0

    for log in logs:
        in_tok = log.input_tokens or 0
        out_tok = log.output_tokens or 0
        cost = _estimate_cost(log.model, in_tok, out_tok)
        total_in += in_tok
        total_out += out_tok
        total_cost += cost

        # By model
        key = log.model
        if key not in model_agg:
            model_agg[key] = {"model": key, "provider": log.provider, "requests": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        model_agg[key]["requests"] += 1
        model_agg[key]["input_tokens"] += in_tok
        model_agg[key]["output_tokens"] += out_tok
        model_agg[key]["cost"] += cost

        # By user
        uid = str(log.user_id) if log.user_id else None
        if uid not in user_agg:
            user = user_map.get(log.user_id) if log.user_id else None
            user_agg[uid] = {
                "user_id": uid,
                "user_name": user.name if user else None,
                "user_email": user.email if user else None,
                "requests": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
            }
        user_agg[uid]["requests"] += 1
        user_agg[uid]["input_tokens"] += in_tok
        user_agg[uid]["output_tokens"] += out_tok
        user_agg[uid]["cost"] += cost

        # By day
        day_key = log.timestamp.strftime("%Y-%m-%d")
        if day_key not in day_agg:
            day_agg[day_key] = {"date": day_key, "requests": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        day_agg[day_key]["requests"] += 1
        day_agg[day_key]["input_tokens"] += in_tok
        day_agg[day_key]["output_tokens"] += out_tok
        day_agg[day_key]["cost"] += cost

    return CostingSummary(
        period=period,
        total_requests=len(logs),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        estimated_cost_usd=round(total_cost, 6),
        by_model=sorted(
            [ModelCost(estimated_cost_usd=round(v["cost"], 6), **{k: v[k] for k in ("model", "provider", "requests", "input_tokens", "output_tokens")}) for v in model_agg.values()],
            key=lambda x: x.estimated_cost_usd, reverse=True,
        ),
        by_user=sorted(
            [UserCost(estimated_cost_usd=round(v["cost"], 6), **{k: v[k] for k in ("user_id", "user_name", "user_email", "requests", "input_tokens", "output_tokens")}) for v in user_agg.values()],
            key=lambda x: x.estimated_cost_usd, reverse=True,
        ),
        by_day=sorted(
            [DayCost(estimated_cost_usd=round(v["cost"], 6), **{k: v[k] for k in ("date", "requests", "input_tokens", "output_tokens")}) for v in day_agg.values()],
            key=lambda x: x.date,
        ),
    )


@router.get("/pricing")
async def get_pricing():
    """Return the model pricing table used for estimation."""
    return {
        model: {"input_per_1k": p[0], "output_per_1k": p[1]}
        for model, p in MODEL_PRICING.items()
    }
