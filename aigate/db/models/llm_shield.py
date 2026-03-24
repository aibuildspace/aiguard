from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aigate.db.engine import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LlmShield(Base):
    """User-created LLM-based shield.

    Each row defines a shield that sends the user's prompt to an LLM
    (using a dedicated shield API key) to evaluate whether content
    passes or fails.
    """

    __tablename__ = "llm_shields"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")

    # The system prompt sent to the evaluator LLM
    system_prompt: Mapped[str] = mapped_column(Text)

    # Model to use for evaluation (e.g. gpt-4o-mini, claude-sonnet-4-20250514)
    model: Mapped[str] = mapped_column(String(128), default="gpt-4o-mini")

    # Provider for the shield LLM call (openai or anthropic)
    provider: Mapped[str] = mapped_column(String(32), default="openai")

    # Default action when the LLM flags content
    default_action: Mapped[str] = mapped_column(String(32), default="warn")
    severity: Mapped[str] = mapped_column(String(32), default="medium")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
