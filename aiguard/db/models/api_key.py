from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiguard.db.engine import Base

if TYPE_CHECKING:
    from aiguard.db.models.org import Org
    from aiguard.db.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # The key shown to the user once: "aip_<org_slug>_<32 random hex chars>"
    # key_prefix is first 8 chars — used for O(1) lookup, not secret.
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    # bcrypt hash of the full key
    key_hash: Mapped[str] = mapped_column(String(255))

    label: Mapped[str] = mapped_column(String(255), default="")
    # Which upstream provider this key is bound to ("anthropic" | "openai" | "any")
    provider: Mapped[str] = mapped_column(String(32), default="any")

    # The real upstream API key, Fernet-encrypted at rest.
    # NULL when running in passthrough mode.
    upstream_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Rolling rate-limit counters (reset every minute)
    rpm_counter: Mapped[int] = mapped_column(Integer, default=0)
    rpm_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped[Org] = relationship("Org", back_populates="api_keys")
    user: Mapped[User | None] = relationship("User", back_populates="api_keys")
