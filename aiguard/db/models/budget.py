from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from aiguard.db.engine import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # A budget can be tied to a user, an API key, or both.  At least one must be set.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Monthly budget limit in USD
    monthly_limit_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Whether to actively enforce (block requests over budget) vs just warn
    enforce: Mapped[bool] = mapped_column(Boolean, default=False)

    # Running totals (reset monthly by cron or on-read)
    current_month_usage_usd: Mapped[float] = mapped_column(Float, default=0.0)
    current_month_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    current_month_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    current_month_requests: Mapped[int] = mapped_column(Integer, default=0)

    # Period tracking
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
