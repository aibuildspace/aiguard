from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from aigate.db.engine import async_session_factory
from aigate.db.models.budget import Budget
from aigate.db.models.user import User
from aigate.db.models.api_key import ApiKey
from aigate.db.models.org import Org

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    org_id: str | None = None
    user_id: str | None = None
    api_key_id: str | None = None
    monthly_limit_usd: float = 10.0
    enforce: bool = False


class BudgetUpdate(BaseModel):
    monthly_limit_usd: float | None = None
    enforce: bool | None = None


class BudgetResponse(BaseModel):
    id: str
    org_id: str | None = None
    user_id: str | None = None
    api_key_id: str | None = None
    monthly_limit_usd: float
    enforce: bool
    current_month_usage_usd: float
    current_month_tokens_in: int
    current_month_tokens_out: int
    current_month_requests: int
    period_start: str
    created_at: str
    updated_at: str
    # Enriched fields
    org_name: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    key_label: str | None = None
    key_prefix: str | None = None
    pct_used: float = 0.0


@router.post("", response_model=BudgetResponse, status_code=201)
async def create_budget(data: BudgetCreate):
    if not data.user_id and not data.api_key_id and not data.org_id:
        raise HTTPException(status_code=400, detail="At least one of org_id, user_id, or api_key_id is required")
    async with async_session_factory() as session:
        # Validate references
        if data.org_id:
            org = await session.get(Org, uuid.UUID(data.org_id))
            if not org:
                raise HTTPException(status_code=404, detail="Organization not found")
        if data.user_id:
            user = await session.get(User, uuid.UUID(data.user_id))
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
        if data.api_key_id:
            key = await session.get(ApiKey, uuid.UUID(data.api_key_id))
            if not key:
                raise HTTPException(status_code=404, detail="API key not found")
        # Check no duplicate
        q = select(Budget)
        if data.org_id and not data.user_id and not data.api_key_id:
            q = q.where(
                Budget.org_id == uuid.UUID(data.org_id),
                Budget.user_id.is_(None),
                Budget.api_key_id.is_(None),
            )
        elif data.user_id and not data.api_key_id:
            q = q.where(Budget.user_id == uuid.UUID(data.user_id), Budget.api_key_id.is_(None))
        elif data.api_key_id and not data.user_id:
            q = q.where(Budget.api_key_id == uuid.UUID(data.api_key_id), Budget.user_id.is_(None))
        else:
            q = q.where(Budget.user_id == uuid.UUID(data.user_id), Budget.api_key_id == uuid.UUID(data.api_key_id))
        existing = await session.execute(q)
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Budget already exists for this target")
        budget = Budget(
            org_id=uuid.UUID(data.org_id) if data.org_id else None,
            user_id=uuid.UUID(data.user_id) if data.user_id else None,
            api_key_id=uuid.UUID(data.api_key_id) if data.api_key_id else None,
            monthly_limit_usd=data.monthly_limit_usd,
            enforce=data.enforce,
        )
        session.add(budget)
        await session.commit()
        await session.refresh(budget)
    return await _to_response(budget)


@router.get("", response_model=list[BudgetResponse])
async def list_budgets(user_id: str | None = None, api_key_id: str | None = None):
    async with async_session_factory() as session:
        q = select(Budget)
        if user_id:
            q = q.where(Budget.user_id == uuid.UUID(user_id))
        if api_key_id:
            q = q.where(Budget.api_key_id == uuid.UUID(api_key_id))
        result = await session.execute(q)
        budgets = result.scalars().all()
    return [await _to_response(b) for b in budgets]


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(budget_id: str):
    async with async_session_factory() as session:
        budget = await session.get(Budget, uuid.UUID(budget_id))
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return await _to_response(budget)


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(budget_id: str, data: BudgetUpdate):
    async with async_session_factory() as session:
        budget = await session.get(Budget, uuid.UUID(budget_id))
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")
        if data.monthly_limit_usd is not None:
            budget.monthly_limit_usd = data.monthly_limit_usd
        if data.enforce is not None:
            budget.enforce = data.enforce
        budget.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(budget)
    return await _to_response(budget)


@router.post("/{budget_id}/reset", response_model=BudgetResponse)
async def reset_budget(budget_id: str):
    """Reset the current month usage counters."""
    async with async_session_factory() as session:
        budget = await session.get(Budget, uuid.UUID(budget_id))
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")
        budget.current_month_usage_usd = 0.0
        budget.current_month_tokens_in = 0
        budget.current_month_tokens_out = 0
        budget.current_month_requests = 0
        budget.period_start = datetime.now(timezone.utc)
        budget.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(budget)
    return await _to_response(budget)


@router.delete("/{budget_id}")
async def delete_budget(budget_id: str):
    async with async_session_factory() as session:
        budget = await session.get(Budget, uuid.UUID(budget_id))
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")
        await session.delete(budget)
        await session.commit()
    return {"status": "ok"}


async def _to_response(budget: Budget) -> BudgetResponse:
    user_name = user_email = key_label = key_prefix = org_name = None
    async with async_session_factory() as session:
        if budget.org_id:
            org = await session.get(Org, budget.org_id)
            if org:
                org_name = org.name
        if budget.user_id:
            user = await session.get(User, budget.user_id)
            if user:
                user_name = user.name
                user_email = user.email
        if budget.api_key_id:
            key = await session.get(ApiKey, budget.api_key_id)
            if key:
                key_label = key.label
                key_prefix = key.key_prefix
    # A $0 limit means "no spending allowed" → always 100% used
    if budget.monthly_limit_usd <= 0:
        pct = 100.0
    else:
        pct = budget.current_month_usage_usd / budget.monthly_limit_usd * 100
    return BudgetResponse(
        id=str(budget.id),
        org_id=str(budget.org_id) if budget.org_id else None,
        user_id=str(budget.user_id) if budget.user_id else None,
        api_key_id=str(budget.api_key_id) if budget.api_key_id else None,
        monthly_limit_usd=budget.monthly_limit_usd,
        enforce=budget.enforce,
        current_month_usage_usd=round(budget.current_month_usage_usd, 6),
        current_month_tokens_in=budget.current_month_tokens_in,
        current_month_tokens_out=budget.current_month_tokens_out,
        current_month_requests=budget.current_month_requests,
        period_start=budget.period_start.isoformat(),
        created_at=budget.created_at.isoformat(),
        updated_at=budget.updated_at.isoformat(),
        org_name=org_name,
        user_name=user_name,
        user_email=user_email,
        key_label=key_label,
        key_prefix=key_prefix,
        pct_used=round(pct, 1),
    )
