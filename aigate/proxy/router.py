"""
Proxy router: mounts provider-specific handlers and the scan+forward pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from aigate.proxy.forwarder import forward_request
from aigate.proxy.middleware import resolve_identity
from aigate.proxy.providers import PROVIDERS
from aigate.proxy.providers.base import AbstractProvider
from aigate.shields.models import PhaseType, ScanContext

logger = logging.getLogger(__name__)

router = APIRouter()

# Env vars that carry real upstream API keys (checked when shield key
# has no encrypted upstream key stored).
_UPSTREAM_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _resolve_upstream_from_env(provider_name: str) -> str | None:
    """Return an upstream API key from environment, or None."""
    var = _UPSTREAM_ENV_VARS.get(provider_name)
    if var:
        val = os.environ.get(var, "").strip()
        if val and not val.startswith("aip_"):
            return val
    return None


def _format_provider_error(
    provider_name: str,
    error_type: str,
    message: str,
    request_id: str | None = None,
) -> dict:
    """Format an error response to match the upstream provider's error shape.

    This ensures SDKs (e.g. Anthropic Python/TS, OpenAI Python) parse the
    error correctly and treat it as an API error rather than embedding the
    raw body into the conversation.
    """
    if provider_name == "anthropic":
        return {
            "type": "error",
            "error": {
                "type": error_type,
                "message": message,
            },
        }
    # OpenAI / generic
    body: dict = {
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if request_id:
        body["error"]["request_id"] = request_id
    return body


@router.api_route(
    "/{provider_prefix}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def proxy_handler(request: Request, provider_prefix: str, path: str):
    full_path = f"/{provider_prefix}/{path}"
    return await _handle_proxy_request(request, full_path)


async def _handle_proxy_request(request: Request, path: str) -> Any:
    t_start = time.monotonic()
    request_id = str(uuid.uuid4())

    # Generate W3C Trace Context compatible IDs
    # trace_id: 32 lowercase hex chars (128-bit)
    # span_id:  16 lowercase hex chars (64-bit)
    trace_id = os.urandom(16).hex()
    span_id = os.urandom(8).hex()
    # Check for incoming W3C traceparent header to propagate
    parent_span_id: str | None = None
    incoming_traceparent = request.headers.get("traceparent")
    if incoming_traceparent:
        parts = incoming_traceparent.split("-")
        if len(parts) >= 4 and len(parts[1]) == 32:
            trace_id = parts[1]        # inherit upstream trace
            parent_span_id = parts[2]  # their span becomes our parent

    # Find matching provider
    provider: AbstractProvider | None = None
    for p in PROVIDERS:
        if path.startswith(p.base_path):
            provider = p
            break

    if provider is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"No provider for path: {path}"}},
        )

    # Auth resolution
    try:
        identity = await resolve_identity(request)
    except Exception as exc:
        # HTTPException will propagate; re-raise
        raise

    # ── Budget enforcement (pre-request) ──────────────────────────────
    budget_block = await _check_budget_enforcement(identity)
    if budget_block is not None:
        _write_audit_log(
            request_id=request_id,
            identity=identity,
            provider=provider.name,
            model="",
            path=path,
            outcome="blocked",
            findings=[],
            http_status=402,
            proxy_latency_ms=int((time.monotonic() - t_start) * 1000),
            policy={},
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            message_preview="[budget exceeded]",
        )
        error_body = _format_provider_error(
            provider_name=provider.name,
            error_type="budget_exceeded",
            message=budget_block["error"]["message"],
        )
        # Use 402 (Payment Required) instead of 429 so SDKs don't
        # auto-retry endlessly — budget blocks are not transient.
        return JSONResponse(
            status_code=402,
            headers={
                "X-AIGate-Request-ID": request_id,
                "X-AIGate-Trace-ID": trace_id,
                "Retry-After": "86400",
                "traceparent": f"00-{trace_id}-{span_id}-01",
            },
            content=error_body,
        )

    # Parse request body
    try:
        raw_body = await request.body()
        body: dict = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Invalid JSON request body"}},
        )

    # Extract normalized content
    content = provider.extract_content(body)
    policy = identity.merged_policy() if hasattr(identity, "merged_policy") else {}

    # Build scan context
    context = ScanContext(
        request_id=request_id,
        org_id=identity.org_id,
        user_id=identity.user_id,
        provider=provider.name,
        model=content.get("model", ""),
        phase="pre_request",
        messages=content.get("messages", []),
        system_prompt=content.get("system_prompt"),
        tool_results=content.get("tool_results", []),
        raw_body=body,
    )

    # Extract first user message for audit preview (max 500 chars)
    _msgs = content.get("messages", [])
    _user_msgs = [m for m in _msgs if isinstance(m, dict) and m.get("role") == "user"]
    msg_preview = None
    if _user_msgs:
        _c = _user_msgs[-1].get("content", "")
        msg_preview = (_c[:500] + "…") if len(_c) > 500 else _c

    # Get shield runner from app state
    shield_runner = request.app.state.shield_runner

    # Determine enabled shields from policy
    enabled_shields = policy.get("enabled_shields", policy.get("enabled_skills"))  # backward compat
    disabled_shields = set(policy.get("disabled_shields", policy.get("disabled_skills", [])))

    # Allow the chat playground (or any client) to disable shields via header
    header_disabled = request.headers.get("x-aigate-disabled-shields", "")
    if header_disabled:
        disabled_shields.update(s.strip() for s in header_disabled.split(",") if s.strip())

    if enabled_shields is not None:
        enabled_shields = [s for s in enabled_shields if s not in disabled_shields]
    else:
        enabled_shields = [
            sid for sid in shield_runner.shields if sid not in disabled_shields
        ]

    shield_overrides = policy.get("shield_params", policy.get("skill_params", {}))

    # Run pre-request scan
    summary = await shield_runner.scan(
        context,
        enabled_shield_ids=enabled_shields,
        shield_overrides=shield_overrides,
    )

    # Handle block
    if summary.outcome == "blocked":
        # Build a short human-readable summary for tools/clients
        # Only list shields whose effective action was actually "block"
        blocking_shields = sorted(
            {r.shield_id for r in summary.results if r.effective_action == "block"}
        )
        short_msg = f"Blocked by {', '.join(blocking_shields)}" if blocking_shields else "Request blocked by security policy"

        # Write full details to audit log (internal only — includes matched_text)
        _write_audit_log(
            request_id=request_id,
            identity=identity,
            provider=provider.name,
            model=content.get("model", ""),
            path=path,
            outcome="blocked",
            findings=summary.all_findings,
            http_status=403,
            proxy_latency_ms=int((time.monotonic() - t_start) * 1000),
            policy=policy,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            message_preview=msg_preview,
            request_body=body if isinstance(body, dict) else None,
        )

        # Client-facing response: short message only, no sensitive data.
        # Full findings are available in the audit log / portal.
        # Format to match the upstream provider's error shape so SDKs
        # handle it as a proper API error (not a conversation response).
        error_body = _format_provider_error(
            provider_name=provider.name,
            error_type="content_policy_violation",
            message=short_msg,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=403,
            headers={
                "X-AIGate-Request-ID": request_id,
                "X-AIGate-Trace-ID": trace_id,
                "traceparent": f"00-{trace_id}-{span_id}-01",
            },
            content=error_body,
        )

    # Use sanitized body if any sanitization ran
    forward_body = summary.modified_body if summary.modified_body else body

    # Resolve upstream key
    upstream_key = identity.upstream_key
    if upstream_key is None:
        # No stored upstream key — try to find one:
        # 1. If the client sent a real (non-shield) key, use it as-is
        raw_auth = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if raw_auth and not raw_auth.startswith("aip_"):
            upstream_key = raw_auth
        else:
            # 2. Fall back to provider-specific env var
            upstream_key = _resolve_upstream_from_env(provider.name) or raw_auth

    upstream_url = provider.upstream_url(path)

    # Build warning headers
    extra_headers: dict[str, str] = {
        "X-AIGate-Request-ID": request_id,
        "X-AIGate-Trace-ID": trace_id,
        "X-AIGate-Span-ID": span_id,
        "traceparent": f"00-{trace_id}-{span_id}-01",
    }
    if summary.outcome in ("warned", "sanitized"):
        shields_triggered = ",".join({f.shield_id for f in summary.all_findings})
        extra_headers["X-AIGate-Warning"] = f"Shields triggered: {shields_triggered}"
        extra_headers["X-AIGate-Outcome"] = summary.outcome
        # Include findings summary so the portal can display details
        # Redact matched_text to avoid leaking sensitive content in headers
        import json as _json
        warned_findings = [
            {
                "shield_id": f.shield_id,
                "pattern_id": f.pattern_id,
                "severity": f.severity,
                "action": f.action,
            }
            for f in summary.all_findings
        ]
        extra_headers["X-AIGate-Findings"] = _json.dumps(warned_findings)

    # For streaming requests, inject stream_options to get usage data
    # (only valid for the Chat Completions API; Responses API rejects it)
    is_streaming = isinstance(forward_body, dict) and forward_body.get("stream", False)
    if is_streaming and isinstance(forward_body, dict) and provider.name == "openai" and "chat/completions" in path:
        forward_body.setdefault("stream_options", {})["include_usage"] = True

    # For OpenAI Responses API: ensure store=true so response IDs can be
    # referenced in multi-turn conversations (otherwise OpenAI returns 404
    # when the client passes a previous rs_... ID in follow-up requests)
    if isinstance(forward_body, dict) and provider.name == "openai" and "/responses" in path:
        forward_body.setdefault("store", True)

    # Build a callback for deferred audit (streaming only)
    _model = content.get("model", "")

    def _on_stream_complete(in_tok: int | None, out_tok: int | None) -> None:
        """Called from the streaming generator when SSE stream ends."""
        proxy_latency_ms = int((time.monotonic() - t_start) * 1000)
        _write_audit_log(
            request_id=request_id,
            identity=identity,
            provider=provider.name,
            model=_model,
            path=path,
            outcome=summary.outcome,
            findings=summary.all_findings,
            http_status=200,  # streaming always starts with 200
            proxy_latency_ms=proxy_latency_ms,
            upstream_latency_ms=timing.get("upstream_latency_ms"),
            policy=policy,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            message_preview=msg_preview,
            input_tokens=in_tok,
            output_tokens=out_tok,
            request_body=forward_body if isinstance(forward_body, dict) else None,
            response_body=None,
        )

    # Forward to upstream
    response, timing = await forward_request(
        request=request,
        upstream_url=upstream_url,
        upstream_key=upstream_key,
        body=forward_body,
        on_stream_complete=_on_stream_complete if is_streaming else None,
    )

    # Retry once for stale response references on the Responses API.
    # When OpenClaw (or any client) references an rs_... ID from a response
    # that was created without store=true, OpenAI returns 404.  Strip the
    # stale reference and retry so the conversation can continue.
    if (
        response.status_code == 404
        and isinstance(forward_body, dict)
        and "/responses" in path
    ):
        stripped = False

        # 1. Top-level previous_response_id
        if "previous_response_id" in forward_body:
            stale_id = forward_body.pop("previous_response_id")
            stripped = True

        # 2. Stale rs_... items embedded in input[] (e.g. reasoning refs)
        input_items = forward_body.get("input")
        if isinstance(input_items, list):
            cleaned = []
            for item in input_items:
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].startswith("rs_"):
                    stripped = True
                    continue
                cleaned.append(item)
            if stripped:
                forward_body["input"] = cleaned

        if stripped:
            response, timing = await forward_request(
                request=request,
                upstream_url=upstream_url,
                upstream_key=upstream_key,
                body=forward_body,
                on_stream_complete=_on_stream_complete if is_streaming else None,
            )

    # Add proxy headers to response
    for k, v in extra_headers.items():
        response.headers[k] = v

    # When upstream returned a non-2xx error on a streaming request, the
    # forwarder now falls back to a buffered JSONResponse.  Detect that so
    # we write the audit log synchronously instead of via the streaming
    # callback (which already fired with None/None).
    is_buffered_error = is_streaming and timing.get("response_body") is not None

    if not is_streaming or is_buffered_error:
        # Extract token counts from buffered response
        input_tokens = None
        output_tokens = None
        resp_body = timing.get("response_body")
        if resp_body and isinstance(resp_body, dict):
            input_tokens, output_tokens = provider.extract_token_counts(resp_body)

        # Audit log (fire-and-forget)
        proxy_latency_ms = int((time.monotonic() - t_start) * 1000)
        _write_audit_log(
            request_id=request_id,
            identity=identity,
            provider=provider.name,
            model=_model,
            path=path,
            outcome=summary.outcome if not is_buffered_error else "error",
            findings=summary.all_findings,
            http_status=response.status_code,
            proxy_latency_ms=proxy_latency_ms,
            upstream_latency_ms=timing.get("upstream_latency_ms"),
            policy=policy,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            message_preview=msg_preview,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_body=forward_body if isinstance(forward_body, dict) else None,
            response_body=resp_body if resp_body and isinstance(resp_body, dict) else None,
        )

    return response


def _write_audit_log(
    request_id: str,
    identity: Any,
    provider: str,
    model: str,
    path: str,
    outcome: str,
    findings: list,
    http_status: int,
    proxy_latency_ms: int,
    upstream_latency_ms: int | None = None,
    policy: dict | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    message_preview: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    request_body: dict | None = None,
    response_body: dict | None = None,
) -> None:
    """Fire-and-forget audit log write + budget accumulation."""
    import asyncio

    async def _write():
        try:
            from datetime import datetime, timezone
            from aigate.db.engine import async_session_factory
            from aigate.db.models.audit_log import AuditLog

            # Ensure passthrough org exists if needed
            _org_id = identity.api_key.org_id
            await _ensure_passthrough_org(_org_id)

            shields_triggered = [
                {"shield_id": f.shield_id, "pattern_id": f.pattern_id, "action": f.action}
                for f in findings
            ]

            log = AuditLog(
                request_id=request_id,
                org_id=identity.api_key.org_id,
                user_id=identity.api_key.user_id,
                api_key_id=identity.api_key.id,
                provider=provider,
                model=model,
                endpoint=path,
                scan_outcome=outcome,
                skills_triggered=shields_triggered,
                http_status=http_status,
                proxy_latency_ms=proxy_latency_ms,
                upstream_latency_ms=upstream_latency_ms,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                message_preview=message_preview,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_us=proxy_latency_ms * 1000 if proxy_latency_ms else None,
                request_body_redacted=request_body,
                response_body_redacted=response_body,
            )

            async with async_session_factory() as session:
                session.add(log)
                await session.commit()
        except Exception as exc:
            logger.debug("Audit log write failed: %s", exc)

        # Export OTLP trace (best-effort)
        try:
            from aigate.observability.otlp import export_trace
            shields_list = [f.shield_id for f in findings] if findings else []
            await export_trace(
                trace_id=trace_id or "",
                span_id=span_id or "",
                parent_span_id=parent_span_id,
                request_id=request_id,
                provider=provider,
                model=model,
                endpoint=path,
                scan_outcome=outcome,
                http_status=http_status,
                proxy_latency_ms=proxy_latency_ms,
                upstream_latency_ms=upstream_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                shields_triggered=shields_list,
                message_preview=message_preview,
                request_body=request_body,
                response_body=response_body,
            )
        except Exception as exc:
            logger.debug("OTLP trace export failed: %s", exc)

        # Update budget counters (best-effort)
        try:
            await _accumulate_budget(
                identity=identity,
                model=model,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
            )
        except Exception as exc:
            logger.debug("Budget accumulation failed: %s", exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write())
    except RuntimeError:
        pass  # No event loop (e.g., in tests)


# ── Budget enforcement (pre-request) ─────────────────────────────────────────

import uuid as _uuid


async def _check_budget_enforcement(identity: Any) -> dict | None:
    """
    Check whether any enforcing budget attached to this identity's API key,
    user, or org has been exceeded.  Returns an error dict to send back if
    the request must be blocked, or None if the request may proceed.

    Covers both normal (aip_ key) and passthrough (direct upstream key) modes.
    In passthrough mode, org-level budgets are still enforced.
    """
    from sqlalchemy import select, or_
    from aigate.db.engine import async_session_factory
    from aigate.db.models.budget import Budget

    api_key_id = identity.api_key.id
    user_id = identity.api_key.user_id
    org_id = getattr(identity.api_key, "org_id", None)
    is_passthrough = api_key_id == _PASSTHROUGH_KEY_UUID

    try:
        async with async_session_factory() as session:
            conditions = []

            if is_passthrough:
                # Passthrough mode: no real user/key identity, so check
                # ALL enforcing budgets.  This ensures passthrough traffic
                # (e.g. Claude Code with a direct API key) is blocked when
                # ANY budget is exceeded — whether org-scoped or key-scoped.
                result = await session.execute(
                    select(Budget).where(
                        Budget.enforce == True,  # noqa: E712
                    )
                )
            else:
                # Normal mode: check per-key, per-user, and per-org budgets
                if user_id:
                    conditions.append(Budget.user_id == user_id)
                conditions.append(Budget.api_key_id == api_key_id)
                if org_id:
                    # Org-level budgets (org_id set, user_id & api_key_id NULL)
                    conditions.append(
                        (Budget.org_id == org_id)
                        & Budget.user_id.is_(None)
                        & Budget.api_key_id.is_(None)
                    )
                result = await session.execute(
                    select(Budget).where(or_(*conditions))
                )

            budgets = result.scalars().all()

            for b in budgets:
                if not b.enforce:
                    continue
                if b.current_month_usage_usd >= b.monthly_limit_usd:
                    limit = b.monthly_limit_usd
                    used = round(b.current_month_usage_usd, 4)
                    scope = "org" if (b.user_id is None and b.api_key_id is None) else "key/user"
                    logger.warning(
                        "Budget exceeded (%s): limit=$%.2f used=$%.4f key=%s",
                        scope, limit, used, str(api_key_id)[:8],
                    )
                    return {
                        "error": {
                            "type": "budget_exceeded",
                            "message": f"Monthly budget exceeded (${used:.4f} / ${limit:.2f})",
                        }
                    }
    except Exception as exc:
        # Fail-closed: if we can't check budgets, block the request to be safe
        logger.warning("Budget enforcement check failed (blocking request): %s", exc)
        return {
            "error": {
                "type": "budget_check_error",
                "message": "Unable to verify budget — request blocked as a precaution",
            }
        }

    return None


# ── Budget accumulation ──────────────────────────────────────────────────────

# Must match _PASSTHROUGH_ORG_ID / _PASSTHROUGH_KEY_ID in middleware.py
_PASSTHROUGH_ORG_UUID = _uuid.UUID("00000000-0000-0000-0000-000000000000")
_PASSTHROUGH_KEY_UUID = _uuid.UUID("00000000-0000-0000-0000-000000000001")

_passthrough_org_ensured = False


async def _ensure_passthrough_org(org_id) -> None:
    """Create the passthrough org row if it doesn't exist (idempotent)."""
    global _passthrough_org_ensured
    if _passthrough_org_ensured:
        return
    if org_id != _PASSTHROUGH_ORG_UUID:
        return  # real org, nothing to do
    try:
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org

        async with async_session_factory() as session:
            existing = await session.get(Org, _PASSTHROUGH_ORG_UUID)
            if not existing:
                org = Org(
                    id=_PASSTHROUGH_ORG_UUID,
                    name="Passthrough",
                    slug="passthrough",
                    policy={},
                )
                session.add(org)
                await session.commit()
                logger.info("Created passthrough org for audit logging")
        _passthrough_org_ensured = True
    except Exception as exc:
        logger.debug("Failed to ensure passthrough org: %s", exc)


# Inline pricing table (same as costing.py)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":      (0.00015, 0.0006),
    "gpt-4o":           (0.0025,  0.01),
    "gpt-4.1-mini":     (0.0004,  0.0016),
    "gpt-4.1":          (0.002,   0.008),
    "gpt-5.1-codex":    (0.002,   0.008),
    "o3-mini":          (0.0011,  0.0044),
    "claude-sonnet-4-20250514":   (0.003, 0.015),
    "claude-haiku-4-20250414":    (0.0008, 0.004),
    "claude-opus-4-20250514":     (0.015, 0.075),
}
_DEFAULT_PRICING = (0.002, 0.008)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single request."""
    in_rate, out_rate = _MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens / 1000 * in_rate) + (output_tokens / 1000 * out_rate)


async def _accumulate_budget(
    identity: Any,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Add token counts and estimated cost to any matching budgets."""
    from sqlalchemy import select, or_
    from aigate.db.engine import async_session_factory
    from aigate.db.models.budget import Budget

    cost_usd = _estimate_cost(model, input_tokens, output_tokens)
    user_id = identity.api_key.user_id
    api_key_id = identity.api_key.id
    org_id = getattr(identity.api_key, "org_id", None)
    is_passthrough = api_key_id == _PASSTHROUGH_KEY_UUID

    async with async_session_factory() as session:
        if is_passthrough:
            # Passthrough mode: accumulate to ALL budgets so that
            # passthrough usage is tracked everywhere (same logic as
            # the enforcement check).
            result = await session.execute(select(Budget))
        else:
            conditions = []
            if user_id:
                conditions.append(Budget.user_id == user_id)
            conditions.append(Budget.api_key_id == api_key_id)
            if org_id:
                # Also accumulate to org-level budgets
                conditions.append(
                    (Budget.org_id == org_id)
                    & Budget.user_id.is_(None)
                    & Budget.api_key_id.is_(None)
                )
            result = await session.execute(select(Budget).where(or_(*conditions)))

        budgets = result.scalars().all()

        for b in budgets:
            b.current_month_usage_usd += cost_usd
            b.current_month_tokens_in += input_tokens
            b.current_month_tokens_out += output_tokens
            b.current_month_requests += 1

        if budgets:
            await session.commit()
