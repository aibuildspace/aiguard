from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aiguard.config import settings
from aiguard.observability.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    configure_logging(settings.log_level)

    # Init DB (create tables on first run)
    from aiguard.db.engine import init_db
    await init_db()
    logger.info("Database initialized")

    # Load shields
    from aiguard.shields.runner import ShieldRunner
    runner = ShieldRunner(settings.shields_dir_list)
    app.state.shield_runner = runner

    # Load LLM shields from DB
    from sqlalchemy import select, func
    from aiguard.db.engine import async_session_factory
    from aiguard.db.models.llm_shield import LlmShield

    async with async_session_factory() as session:
        total = (await session.execute(select(func.count(LlmShield.id)))).scalar() or 0
        active = (await session.execute(
            select(func.count(LlmShield.id)).where(LlmShield.enabled == True)
        )).scalar() or 0
        if total:
            names_result = await session.execute(select(LlmShield.name, LlmShield.enabled))
            llm_shields_info = names_result.all()
            names_str = ", ".join(
                f"{name} ({'active' if enabled else 'disabled'})"
                for name, enabled in llm_shields_info
            )
            logger.info("LLM shields: %s", names_str)
        else:
            logger.info("LLM shields: none configured")

    file_count = len(runner.shields)
    logger.info(
        "Total: %d shields (%d file-based, %d LLM — %d active)",
        file_count + total, file_count, total, active,
    )

    yield

    # Shutdown: close HTTP client pool
    from aiguard.proxy.forwarder import close_client
    await close_client()
    logger.info("AIGuard shutdown complete")


def create_app() -> FastAPI:
    is_prod = settings.mode == "prod"

    # ── Prod-mode startup validation (belt-and-suspenders: CLI checks first,
    #    but this catches direct uvicorn / programmatic use) ─────────────────
    if is_prod:
        if not settings.admin_api_key:
            import sys
            logger.critical(
                "GUARD_ADMIN_API_KEY must be set in production mode. "
                "Refusing to start with an unprotected admin API."
            )
            sys.exit(1)
        if not settings.encryption_key:
            logger.warning(
                "GUARD_ENCRYPTION_KEY is not set — upstream keys are stored "
                "without encryption. Set it for production use."
            )

    app = FastAPI(
        title="AIGuard",
        description="Anti-virus for AI — security middleware proxy for LLM APIs",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if (settings.debug and not is_prod) else None,
        redoc_url=None,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    if is_prod:
        # Prod: locked-down origins (default empty → no browser access)
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] if settings.cors_origins else []
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Admin-Key"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Health check (always available)
    from aiguard.api.endpoints.health import router as health_router
    app.include_router(health_router)

    # ── Management API ────────────────────────────────────────────────────
    if settings.admin_api_enabled:
        if is_prod:
            from aiguard.api.router import build_prod_router
            app.include_router(build_prod_router(), prefix="/api/v1")
            logger.info("Admin API: PROD (read-only endpoints, key required)")
        else:
            from aiguard.api.router import build_dev_router
            app.include_router(build_dev_router(), prefix="/api/v1")
            logger.info("Admin API: DEV (all endpoints)")

    # ── Portal (dev mode only) ────────────────────────────────────────────
    if not is_prod:
        from pathlib import Path
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        portal_dir = Path(__file__).parent / "portal"

        @app.get("/portal")
        async def portal_index():
            return FileResponse(portal_dir / "index.html")

        app.mount("/portal/static", StaticFiles(directory=portal_dir), name="portal-static")
    else:
        logger.info("Portal: DISABLED (prod mode)")

    # Proxy routes (catch-all, mounted last)
    from aiguard.proxy.router import router as proxy_router
    app.include_router(proxy_router)

    return app


app = create_app()
