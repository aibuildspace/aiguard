from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from aigate.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite-specific: allow same connection across threads (needed for CLI)
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables. Called on first startup."""
    from aigate.db.models import audit_log, api_key, org, shield_config, user, budget, llm_shield  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate: add new columns to existing tables (SQLite safe)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn) -> None:
    """Add columns that don't exist yet (lightweight auto-migration)."""
    import sqlalchemy as sa
    from sqlalchemy import inspect as sa_inspect, text

    inspector = sa_inspect(conn)

    # Map of table -> list of (column_name, column_type_sql)
    migrations = {
        "audit_logs": [
            ("trace_id", "VARCHAR(32)"),
            ("span_id", "VARCHAR(16)"),
            ("parent_span_id", "VARCHAR(16)"),
            ("duration_us", "INTEGER"),
            ("scan_duration_us", "INTEGER"),
            ("message_preview", "TEXT"),
        ],
        "budgets": [
            ("org_id", "VARCHAR(36)"),
        ],
    }

    for table_name, columns in migrations.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name, col_type in columns:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
