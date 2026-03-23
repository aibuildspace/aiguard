from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aiguard.db.engine import Base

if TYPE_CHECKING:
    from aiguard.db.models.api_key import ApiKey
    from aiguard.db.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # JSON policy blob — validated against OrgPolicy pydantic model at read time.
    # Stores: enabled_shields, disabled_shields, pii_action, injection_action,
    #         rate_limit_rpm, allowed_models, store_request_body, store_response_body
    policy: Mapped[dict] = mapped_column(JSON, default=dict)

    users: Mapped[list[User]] = relationship("User", back_populates="org", lazy="selectin")
    api_keys: Mapped[list[ApiKey]] = relationship("ApiKey", back_populates="org", lazy="selectin")
