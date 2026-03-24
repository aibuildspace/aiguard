from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from aigate.db.engine import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    api_key_id: Mapped[uuid.UUID] = mapped_column()

    provider: Mapped[str] = mapped_column(String(32))   # "anthropic" | "openai"
    model: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(255))

    # UUID for correlating proxy ↔ upstream logs
    request_id: Mapped[str] = mapped_column(String(36), index=True)

    # W3C Trace Context — standard 32-hex trace_id + 16-hex span_id
    # Compatible with OpenTelemetry / Grafana Tempo
    trace_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Scan outcome: "clean" | "warned" | "blocked" | "sanitized"
    scan_outcome: Mapped[str] = mapped_column(String(32), index=True)
    # JSON list of {"shield_id": ..., "pattern_id": ..., "action": ...}
    skills_triggered: Mapped[list] = mapped_column(JSON, default=list)

    # Token counts (populated from upstream response)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Latency in milliseconds
    proxy_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upstream_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    http_status: Mapped[int] = mapped_column(Integer)

    # First user message (truncated preview for audit display)
    message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Duration breakdown (microseconds for OTel compat)
    duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional redacted bodies — gated by org policy
    request_body_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_body_redacted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
