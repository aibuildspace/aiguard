"""
Activation endpoints: configure external tools (Claude Code CLI, OpenClaw)
to route through the AIGuard proxy.

Activation only sets the proxy URL in tool config files. Tools keep their
existing API keys which flow through the proxy in passthrough mode.

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │  Helpers (reusable, stateless)                          │
    │  ├── _proxy_base_url()                                  │
    │  └── _detect_tool()   — is a tool installed?            │
    ├─────────────────────────────────────────────────────────┤
    │  Tool Configurators (one per tool, pure I/O)            │
    │  ├── _check_claude_code()   / _check_openclaw()         │
    │  ├── _write_claude_code()   / _write_openclaw()         │
    │  └── _remove_claude_code()  / _remove_openclaw()        │
    ├─────────────────────────────────────────────────────────┤
    │  Endpoints (thin wiring)                                │
    │  ├── GET  /activations                                  │
    │  ├── POST /activations/claude-code/activate             │
    │  ├── POST /activations/claude-code/deactivate           │
    │  ├── POST /activations/openclaw/activate                │
    │  └── POST /activations/openclaw/deactivate              │
    └─────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from aiguard.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activations", tags=["activations"])

# ── Constants ─────────────────────────────────────────────────────────────

CLAUDE_CODE_SETTINGS = Path.home() / ".claude" / "settings.json"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS — reusable, stateless
# ═══════════════════════════════════════════════════════════════════════════

def _proxy_base_url() -> str:
    """Return the proxy base URL from server configuration."""
    host = settings.host
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{settings.port}"


def _detect_tool(tool: str) -> bool:
    """Check whether a tool binary or config directory exists."""
    if tool == "claude_code":
        return shutil.which("claude") is not None or (Path.home() / ".claude").is_dir()
    if tool == "openclaw":
        return shutil.which("openclaw") is not None or (Path.home() / ".openclaw").is_dir()
    return False


# ═══════════════════════════════════════════════════════════════════════════
# TOOL CONFIGURATORS — pure I/O, one pair per tool
# ═══════════════════════════════════════════════════════════════════════════

def _check_claude_code(proxy_base: str) -> dict:
    """Return status dict for Claude Code CLI."""
    installed = _detect_tool("claude_code")
    try:
        if not CLAUDE_CODE_SETTINGS.exists():
            return {
                "installed": installed,
                "active": False,
                "detail": "Not configured" if installed else "Claude Code not detected",
            }
        data = json.loads(CLAUDE_CODE_SETTINGS.read_text())
        env = data.get("env", {})
        current_url = env.get("ANTHROPIC_BASE_URL", "")
        current_key = env.get("ANTHROPIC_API_KEY", "")
        expected = f"{proxy_base}/anthropic"

        if current_url == expected:
            return {
                "installed": True,
                "active": True,
                "detail": f"ANTHROPIC_BASE_URL → {expected}",
            }
        elif current_url:
            return {
                "installed": True,
                "active": False,
                "detail": f"ANTHROPIC_BASE_URL → {current_url} (different proxy)",
            }
        return {"installed": True, "active": False, "detail": "ANTHROPIC_BASE_URL not set"}
    except Exception as e:
        return {"installed": installed, "active": False, "detail": f"Error: {e}"}


def _write_claude_code(proxy_url: str) -> dict:
    """
    Set ANTHROPIC_BASE_URL in ~/.claude/settings.json to route through proxy.
    Leaves ANTHROPIC_API_KEY untouched — passthrough mode forwards it.
    """
    CLAUDE_CODE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if CLAUDE_CODE_SETTINGS.exists():
        data = json.loads(CLAUDE_CODE_SETTINGS.read_text())

    env = data.setdefault("env", {})
    env["ANTHROPIC_BASE_URL"] = f"{proxy_url}/anthropic"

    CLAUDE_CODE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    return {"ok": True, "detail": f"Set ANTHROPIC_BASE_URL → {proxy_url}/anthropic"}


def _remove_claude_code() -> dict:
    """Remove ANTHROPIC_BASE_URL from ~/.claude/settings.json."""
    if not CLAUDE_CODE_SETTINGS.exists():
        return {"ok": True, "detail": "No settings file to modify"}

    data = json.loads(CLAUDE_CODE_SETTINGS.read_text())
    env = data.get("env", {})
    removed = []
    if "ANTHROPIC_BASE_URL" in env:
        del env["ANTHROPIC_BASE_URL"]
        removed.append("ANTHROPIC_BASE_URL")
    if not env:
        data.pop("env", None)

    CLAUDE_CODE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    return {"ok": True, "detail": f"Removed {', '.join(removed) or 'nothing'} from settings"}


def _check_openclaw(proxy_base: str) -> dict:
    """
    Return status dict for OpenClaw by inspecting models.providers
    in ~/.openclaw/openclaw.json.
    """
    installed = _detect_tool("openclaw")
    try:
        if not OPENCLAW_CONFIG.exists():
            return {
                "installed": installed,
                "active": False,
                "detail": "Not configured" if installed else "OpenClaw not detected",
            }
        data = json.loads(OPENCLAW_CONFIG.read_text())
        providers = data.get("models", {}).get("providers", {})

        # Check if any provider has our proxy baseUrl
        for name, prov_cfg in providers.items():
            base_url = prov_cfg.get("baseUrl", "")
            api_key = prov_cfg.get("apiKey", "")

            if not base_url:
                continue

            # Check if baseUrl points at our proxy
            if base_url.startswith(proxy_base):
                return {
                    "installed": True,
                    "active": True,
                    "detail": f"models.providers.{name} → {base_url}",
                }

        return {"installed": installed, "active": False, "detail": "models.providers not proxied"}
    except Exception as e:
        return {"installed": installed, "active": False, "detail": f"Error: {e}"}


def _write_openclaw(proxy_url: str) -> dict:
    """
    Set proxy baseUrl in models.providers.openai in ~/.openclaw/openclaw.json.
    Leaves apiKey untouched — passthrough mode forwards it.
    """
    if not OPENCLAW_CONFIG.exists():
        return {"ok": False, "detail": "openclaw.json not found – run `openclaw onboard` first"}

    data = json.loads(OPENCLAW_CONFIG.read_text())

    # Ensure models.providers.openai exists
    models = data.setdefault("models", {})
    providers = models.setdefault("providers", {})
    openai_cfg = providers.setdefault("openai", {})

    # Set proxy base URL only
    openai_cfg["baseUrl"] = f"{proxy_url}/openai/v1"
    if "models" not in openai_cfg:
        openai_cfg["models"] = []

    OPENCLAW_CONFIG.write_text(json.dumps(data, indent=2) + "\n")

    return {"ok": True, "detail": f"Set models.providers.openai.baseUrl → {proxy_url}/openai/v1"}


def _remove_openclaw() -> dict:
    """
    Remove proxy baseUrl from models.providers in ~/.openclaw/openclaw.json.
    Leaves apiKey untouched.
    """
    if not OPENCLAW_CONFIG.exists():
        return {"ok": True, "detail": "No config file to modify"}

    data = json.loads(OPENCLAW_CONFIG.read_text())
    providers = data.get("models", {}).get("providers", {})
    changed = False

    for name in ("openai", "anthropic"):
        prov_cfg = providers.get(name, {})
        if not prov_cfg:
            continue

        # Remove proxy baseUrl only
        if "baseUrl" in prov_cfg:
            del prov_cfg["baseUrl"]
            changed = True

        # Clean up _original_apiKey backup if present (legacy)
        prov_cfg.pop("_original_apiKey", None)

    OPENCLAW_CONFIG.write_text(json.dumps(data, indent=2) + "\n")

    detail = "Removed proxy baseUrl from providers" if changed else "No proxy config found"
    return {"ok": True, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class ActivateRequest(BaseModel):
    """Kept for API compatibility; fields are currently unused."""
    pass


class ActivateResult(BaseModel):
    ok: bool
    detail: str


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS — thin wiring layer
# ═══════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_activation_status():
    """Check which tools are currently configured to use the proxy."""
    proxy_base = _proxy_base_url()
    return {
        "proxy_url": proxy_base,
        "playground": {"active": True, "detail": "Built-in — always available"},
        "claude_code": _check_claude_code(proxy_base),
        "openclaw": _check_openclaw(proxy_base),
    }


@router.post("/claude-code/activate")
async def activate_claude_code(body: ActivateRequest | None = None) -> ActivateResult:
    """
    Activate Claude Code CLI: set ANTHROPIC_BASE_URL to route through proxy.
    The tool's existing ANTHROPIC_API_KEY is left in place (passthrough mode).
    """
    proxy_base = _proxy_base_url()
    try:
        result = _write_claude_code(proxy_base)
        logger.info("Claude Code activated (proxy URL only)")
        return ActivateResult(ok=result["ok"], detail=result["detail"])
    except Exception as e:
        logger.error("Failed to activate Claude Code: %s", e)
        return ActivateResult(ok=False, detail=str(e))


@router.post("/claude-code/deactivate")
async def deactivate_claude_code() -> ActivateResult:
    """Remove proxy URL from Claude Code settings."""
    try:
        result = _remove_claude_code()
        logger.info("Claude Code deactivated")
        return ActivateResult(ok=result["ok"], detail=result["detail"])
    except Exception as e:
        logger.error("Failed to deactivate Claude Code: %s", e)
        return ActivateResult(ok=False, detail=str(e))


@router.post("/openclaw/activate")
async def activate_openclaw(body: ActivateRequest | None = None) -> ActivateResult:
    """
    Activate OpenClaw: set provider baseUrl to route through proxy.
    The tool's existing API key is left in place (passthrough mode).
    """
    proxy_base = _proxy_base_url()
    try:
        result = _write_openclaw(proxy_base)
        logger.info("OpenClaw activated (proxy URL only)")
        return ActivateResult(ok=result["ok"], detail=result["detail"])
    except Exception as e:
        logger.error("Failed to activate OpenClaw: %s", e)
        return ActivateResult(ok=False, detail=str(e))


@router.post("/openclaw/deactivate")
async def deactivate_openclaw() -> ActivateResult:
    """Remove proxy URL from OpenClaw config."""
    try:
        result = _remove_openclaw()
        logger.info("OpenClaw deactivated")
        return ActivateResult(ok=result["ok"], detail=result["detail"])
    except Exception as e:
        logger.error("Failed to deactivate OpenClaw: %s", e)
        return ActivateResult(ok=False, detail=str(e))
