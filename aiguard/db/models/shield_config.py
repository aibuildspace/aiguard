from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from aiguard.db.engine import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ShieldConfig(Base):
    """Org-level or user-level shield enable/disable + parameter overrides."""

    __tablename__ = "shield_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    # NULL = org-level config; set = user-level override
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Matches the `id` field in shield.yaml
    shield_id: Mapped[str] = mapped_column(String(128), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Override the shield's default_action for this org/user
    action_override: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Custom params merged on top of shield.yaml params for this org/user
    params: Mapped[dict] = mapped_column(JSON, default=dict)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
