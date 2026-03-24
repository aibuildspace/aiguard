from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from aigate.config import settings

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def require_admin(api_key: str | None = Security(_api_key_header)):
    """Validate admin API key.  In prod mode the key is always required."""
    if settings.mode == "prod":
        # Prod: key is mandatory (startup enforces it is set)
        if not api_key or api_key != settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Invalid admin API key")
    # Dev mode: no key required — portal and CLI have full access


# ── Full router (dev mode): every endpoint ────────────────────────────────

def build_dev_router() -> APIRouter:
    """All admin endpoints — full read/write access."""
    r = APIRouter(dependencies=[Depends(require_admin)])

    from aigate.api.endpoints.orgs import router as orgs_router
    from aigate.api.endpoints.users import router as users_router
    from aigate.api.endpoints.api_keys import router as keys_router
    from aigate.api.endpoints.shields import router as shields_router
    from aigate.api.endpoints.audit import router as audit_router
    from aigate.api.endpoints.dashboard import router as dashboard_router
    from aigate.api.endpoints.budgets import router as budgets_router
    from aigate.api.endpoints.costing import router as costing_router
    from aigate.api.endpoints.settings import router as settings_router
    from aigate.api.endpoints.activations import router as activations_router
    from aigate.api.endpoints.llm_shields import router as llm_shields_router

    r.include_router(orgs_router)
    r.include_router(users_router)
    r.include_router(keys_router)
    r.include_router(shields_router)
    r.include_router(audit_router)
    r.include_router(dashboard_router)
    r.include_router(budgets_router)
    r.include_router(costing_router)
    r.include_router(settings_router)
    r.include_router(activations_router)
    r.include_router(llm_shields_router)

    return r


# ── Prod-safe router: read-only monitoring endpoints only ─────────────────

def build_prod_router() -> APIRouter:
    """
    Locked-down admin router for production use.

    Only read-only (GET) endpoints are exposed:
      - /audit          — view audit logs
      - /dashboard      — monitoring stats
      - /budgets        — view budgets & usage (GET only)
      - /costing        — cost summaries & pricing
      - /shields        — list loaded shields (GET only)
      - /orgs           — list organisations (GET only)
      - /users          — list users (GET only)
      - /llm-shields    — list LLM shields (GET only)

    Disabled entirely:
      - /activations    — writes to host filesystem
      - /settings       — mutates runtime config
      - /keys           — API key management

    For endpoints with both GET and POST/PATCH/DELETE, only the GET routes
    are included via thin wrapper routers.
    """
    r = APIRouter(dependencies=[Depends(require_admin)])

    # These are read-only by nature
    from aigate.api.endpoints.dashboard import router as dashboard_router
    from aigate.api.endpoints.costing import router as costing_router

    r.include_router(dashboard_router)
    r.include_router(costing_router)

    # For routers that mix GET + mutating routes, create read-only wrappers
    r.include_router(_read_only_audit())
    r.include_router(_read_only_budgets())
    r.include_router(_read_only_shields())
    r.include_router(_read_only_orgs())
    r.include_router(_read_only_users())
    r.include_router(_read_only_llm_shields())

    return r


def _read_only_audit() -> APIRouter:
    """GET /audit and GET /audit/{id} only — no DELETE."""
    from aigate.api.endpoints.audit import list_audit_logs, get_audit_log, AuditLogResponse
    ro = APIRouter(prefix="/audit", tags=["audit"])
    ro.get("", response_model=list[AuditLogResponse])(list_audit_logs)
    ro.get("/{log_id}", response_model=AuditLogResponse)(get_audit_log)
    return ro


def _read_only_budgets() -> APIRouter:
    """GET /budgets and GET /budgets/{id} only."""
    from aigate.api.endpoints.budgets import list_budgets, get_budget, BudgetResponse
    ro = APIRouter(prefix="/budgets", tags=["budgets"])
    ro.get("", response_model=list[BudgetResponse])(list_budgets)
    ro.get("/{budget_id}", response_model=BudgetResponse)(get_budget)
    return ro


def _read_only_shields() -> APIRouter:
    from aigate.api.endpoints.shields import list_shields, get_shield
    ro = APIRouter(prefix="/shields", tags=["shields"])
    ro.get("")(list_shields)
    ro.get("/{shield_id}")(get_shield)
    return ro


def _read_only_orgs() -> APIRouter:
    from aigate.api.endpoints.orgs import list_orgs, get_org, OrgResponse
    ro = APIRouter(prefix="/orgs", tags=["orgs"])
    ro.get("", response_model=list[OrgResponse])(list_orgs)
    ro.get("/{org_id}", response_model=OrgResponse)(get_org)
    return ro


def _read_only_users() -> APIRouter:
    from aigate.api.endpoints.users import list_users, get_user, UserResponse
    ro = APIRouter(prefix="/users", tags=["users"])
    ro.get("", response_model=list[UserResponse])(list_users)
    ro.get("/{user_id}", response_model=UserResponse)(get_user)
    return ro


def _read_only_llm_shields() -> APIRouter:
    from aigate.api.endpoints.llm_shields import list_llm_shields, get_llm_shield
    ro = APIRouter(prefix="/llm-shields", tags=["llm-shields"])
    ro.get("")(list_llm_shields)
    ro.get("/{shield_id}")(get_llm_shield)
    return ro


# ── Default export (backward-compat for imports) ─────────────────────────

router = build_dev_router()
