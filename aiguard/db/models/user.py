from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiguard.db.engine import Base

if TYPE_CHECKING:
    from aiguard.db.models.api_key import ApiKey
    from aiguard.db.models.org import Org

UserRole = Literal["admin", "member", "readonly"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Per-user policy overrides (merged on top of org policy at request time)
    policy_overrides: Mapped[dict] = mapped_column(JSON, default=dict)

    org: Mapped[Org] = relationship("Org", back_populates="users")
    api_keys: Mapped[list[ApiKey]] = relationship("ApiKey", back_populates="user", lazy="selectin")
