"""
HTTP forwarder: sends the (possibly modified) request to the upstream LLM API
and streams the response back to the client.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, Callable

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from aiguard.config import settings

logger = logging.getLogger(__name__)

_EXCLUDED_REQUEST_HEADERS = {
    "host",
    "authorization",
    "content-length",
    "transfer-encoding",
    "connection",
    "accept-encoding",
}

_EXCLUDED_RESPONSE_HEADERS = {
    "content-encoding",
    "transfer-encoding",
    "connection",
    "content-length",
}

# Shared async client (reused across requests for connection pooling)
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.upstream_connect_timeout,
                read=settings.upstream_read_timeout,
                write=30.0,
                pool=5.0,
            ),
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


async def forward_request(
    request: Request,
    upstream_url: str,
    upstream_key: str,
    body: dict | bytes,
    on_stream_complete: "Callable[[int | None, int | None], None] | None" = None,
) -> tuple[StreamingResponse | JSONResponse, dict]:
    """
    Forward the request to upstream and return the response + timing info.

    Args:
        on_stream_complete: Optional callback invoked when a streaming response
            finishes. Receives (input_tokens, output_tokens).

    Returns:
        (response, timing_dict) where timing_dict has upstream_latency_ms.
    """
    import json

    # Build headers to forward
    forward_headers: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() not in _EXCLUDED_REQUEST_HEADERS:
            forward_headers[k] = v

    # Set upstream Authorization
    forward_headers["authorization"] = f"Bearer {upstream_key}"

    # Serialize body if dict
    if isinstance(body, dict):
        raw_body = json.dumps(body).encode()
        forward_headers["content-type"] = "application/json"
    else:
        raw_body = body

    is_streaming = _is_streaming_request(body if isinstance(body, dict) else {})

    client = get_client()
    t0 = time.monotonic()

    try:
        if is_streaming:
            return await _forward_streaming(
                client, request.method, upstream_url, forward_headers, raw_body, t0,
                on_complete=on_stream_complete,
            )
        else:
            return await _forward_buffered(
                client, request.method, upstream_url, forward_headers, raw_body, t0
            )
    except httpx.TimeoutException:
        return (
            JSONResponse(
                status_code=504,
                content={"error": {"message": "Upstream API timed out", "type": "gateway_timeout"}},
            ),
            {"upstream_latency_ms": int((time.monotonic() - t0) * 1000)},
        )
    except httpx.RequestError as exc:
        logger.error("Upstream request error: %s", exc)
        return (
            JSONResponse(
                status_code=502,
                content={"error": {"message": "Upstream API unreachable", "type": "bad_gateway"}},
            ),
            {"upstream_latency_ms": int((time.monotonic() - t0) * 1000)},
        )


async def _forward_buffered(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    body: bytes,
    t0: float,
) -> tuple[JSONResponse, dict]:
    response = await client.request(method, url, headers=headers, content=body)
    latency_ms = int((time.monotonic() - t0) * 1000)

    # Forward response headers (filtered)
    resp_headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in _EXCLUDED_RESPONSE_HEADERS
    }

    # Parse response body safely — upstream may return non-JSON or compressed data
    content = {}
    try:
        raw = response.content  # bytes already read by client.request()
    except Exception:
        raw = b""
    if raw:
        try:
            import json as _json
            content = _json.loads(raw.decode("utf-8"))
        except Exception:
            try:
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                text = "<binary response>"
            content = {"error": {"message": text, "type": "upstream_error"}}

    return (
        JSONResponse(
            content=content,
            status_code=response.status_code,
            headers=resp_headers,
        ),
        {"upstream_latency_ms": latency_ms, "response_body": content},
    )


async def _forward_streaming(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    body: bytes,
    t0: float,
    on_complete: "Callable[[int | None, int | None], None] | None" = None,
) -> tuple[StreamingResponse | JSONResponse, dict]:
    """
    Stream the upstream response back to the client.

    Opens the upstream connection first to inspect status code and headers.
    If upstream returns an error (non-2xx), falls back to a buffered JSON
    response with the correct status code — this ensures SDKs/CLIs see the
    real error instead of a 200 wrapping an error body.

    For successful streaming responses, parses SSE ``data:`` lines on the
    fly to capture usage/token counts from the final events.  When streaming
    finishes, calls ``on_complete`` (if provided) with (input_tokens,
    output_tokens).
    """
    import json as _json

    timing: dict = {"upstream_latency_ms": int((time.monotonic() - t0) * 1000)}

    # Open the upstream connection — this reads status + headers but not body
    req = client.build_request(method, url, headers=headers, content=body)
    resp = await client.send(req, stream=True)
    timing["upstream_latency_ms"] = int((time.monotonic() - t0) * 1000)

    # ── Non-2xx: fall back to buffered error response ────────────────────
    if resp.status_code >= 400:
        try:
            raw = await resp.aread()
        except Exception:
            raw = b""
        finally:
            await resp.aclose()

        resp_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in _EXCLUDED_RESPONSE_HEADERS
        }

        content = {}
        if raw:
            try:
                content = _json.loads(raw.decode("utf-8"))
            except Exception:
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    text = "<binary response>"
                content = {"error": {"message": text, "type": "upstream_error"}}

        logger.warning(
            "Upstream streaming request returned %d: %s",
            resp.status_code,
            content.get("error", {}).get("message", "")[:200],
        )

        if on_complete:
            try:
                on_complete(None, None)
            except Exception:
                pass

        return (
            JSONResponse(
                content=content,
                status_code=resp.status_code,
                headers=resp_headers,
            ),
            {**timing, "response_body": content},
        )

    # ── 2xx: stream the response back ────────────────────────────────────
    async def stream_gen() -> AsyncGenerator[bytes, None]:
        last_data_lines: list[str] = []
        try:
            buf = b""
            async for chunk in resp.aiter_bytes():
                yield chunk
                # Parse SSE lines to capture usage data
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").strip()
                    if text.startswith("data:"):
                        payload = text[5:].strip()
                        if payload and payload != "[DONE]":
                            last_data_lines.append(payload)
                            if len(last_data_lines) > 5:
                                last_data_lines.pop(0)
        finally:
            await resp.aclose()

            # Extract usage from the last SSE events
            input_tokens = None
            output_tokens = None
            for data_str in reversed(last_data_lines):
                try:
                    obj = _json.loads(data_str)
                except Exception:
                    continue
                # Chat Completions: top-level "usage"
                # Responses API: nested under "response.usage"
                usage = obj.get("usage") or {}
                if not usage:
                    resp_obj = obj.get("response")
                    if isinstance(resp_obj, dict):
                        usage = resp_obj.get("usage") or {}
                if not usage:
                    continue
                # OpenAI Chat: prompt_tokens / completion_tokens
                # OpenAI Responses: input_tokens / output_tokens
                if input_tokens is None:
                    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
                if output_tokens is None:
                    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
                if input_tokens is not None and output_tokens is not None:
                    break

            if on_complete:
                try:
                    on_complete(input_tokens, output_tokens)
                except Exception:
                    pass

    # Forward upstream response headers (filtered) + anti-buffering headers
    resp_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in _EXCLUDED_RESPONSE_HEADERS
    }
    resp_headers["cache-control"] = "no-cache"
    resp_headers["x-accel-buffering"] = "no"      # nginx / Azure proxy
    resp_headers["x-content-type-options"] = "nosniff"

    # Use upstream Content-Type (may be text/event-stream, application/x-ndjson, etc.)
    upstream_content_type = resp.headers.get("content-type", "text/event-stream")

    return (
        StreamingResponse(
            stream_gen(),
            status_code=resp.status_code,
            media_type=upstream_content_type,
            headers=resp_headers,
        ),
        timing,
    )


def _is_streaming_request(body: dict) -> bool:
    return bool(body.get("stream", False))
