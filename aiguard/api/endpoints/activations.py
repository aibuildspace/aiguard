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
OPENCLAW_AUTH_PROFILES = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"


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
            key_info = ""
            if current_key and current_key.startswith("aip_"):
                key_info = f", API_KEY → {current_key[:16]}…"
            elif current_key:
                key_info = ", API_KEY → (non-proxy key)"
            else:
                key_info = ", API_KEY → not set"
            return {
                "installed": True,
                "active": True,
                "detail": f"ANTHROPIC_BASE_URL → {expected}{key_info}",
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


def _write_claude_code(proxy_url: str, api_key: str | None = None) -> dict:
    """
    Set ANTHROPIC_BASE_URL (and optionally ANTHROPIC_API_KEY) in
    ~/.claude/settings.json to route through proxy.
    """
    CLAUDE_CODE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if CLAUDE_CODE_SETTINGS.exists():
        data = json.loads(CLAUDE_CODE_SETTINGS.read_text())

    env = data.setdefault("env", {})
    env["ANTHROPIC_BASE_URL"] = f"{proxy_url}/anthropic"
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    CLAUDE_CODE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    detail = f"Set ANTHROPIC_BASE_URL → {proxy_url}/anthropic"
    if api_key:
        detail += f", ANTHROPIC_API_KEY → {api_key[:16]}…"
    return {"ok": True, "detail": detail}


def _remove_claude_code() -> dict:
    """Remove ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY from ~/.claude/settings.json."""
    if not CLAUDE_CODE_SETTINGS.exists():
        return {"ok": True, "detail": "No settings file to modify"}

    data = json.loads(CLAUDE_CODE_SETTINGS.read_text())
    env = data.get("env", {})
    removed = []
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"):
        if var in env:
            del env[var]
            removed.append(var)
    if not env:
        data.pop("env", None)

    CLAUDE_CODE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    return {"ok": True, "detail": f"Removed {', '.join(removed) or 'nothing'} from settings"}


def _check_openclaw(proxy_base: str) -> dict:
    """
    Return status dict for OpenClaw by inspecting models.providers
    in ~/.openclaw/openclaw.json and auth key from auth-profiles.json.
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

        # Read the actual key from auth-profiles.json
        auth_key = ""
        if OPENCLAW_AUTH_PROFILES.exists():
            auth_data = json.loads(OPENCLAW_AUTH_PROFILES.read_text())
            profile = auth_data.get("profiles", {}).get("openai:default", {})
            auth_key = profile.get("key", "")

        # Check if any provider has our proxy baseUrl
        for name, prov_cfg in providers.items():
            base_url = prov_cfg.get("baseUrl", "")

            if not base_url:
                continue

            # Check if baseUrl points at our proxy
            if base_url.startswith(proxy_base):
                key_info = ""
                if auth_key and auth_key.startswith("aip_"):
                    key_info = f", apiKey → {auth_key[:16]}…"
                elif auth_key:
                    key_info = ", apiKey → (non-proxy key)"
                else:
                    key_info = ", apiKey → not set"
                return {
                    "installed": True,
                    "active": True,
                    "detail": f"models.providers.{name} → {base_url}{key_info}",
                }

        return {"installed": installed, "active": False, "detail": "models.providers not proxied"}
    except Exception as e:
        return {"installed": installed, "active": False, "detail": f"Error: {e}"}


def _write_openclaw(proxy_url: str, api_key: str | None = None) -> dict:
    """
    Set proxy baseUrl in models.providers.openai in ~/.openclaw/openclaw.json
    and write API key to auth-profiles.json (where OpenClaw actually reads it).
    """
    if not OPENCLAW_CONFIG.exists():
        return {"ok": False, "detail": "openclaw.json not found – run `openclaw onboard` first"}

    data = json.loads(OPENCLAW_CONFIG.read_text())

    # Ensure models.providers.openai exists
    models = data.setdefault("models", {})
    providers = models.setdefault("providers", {})
    openai_cfg = providers.setdefault("openai", {})

    # Set proxy base URL
    openai_cfg["baseUrl"] = f"{proxy_url}/openai/v1"
    if "models" not in openai_cfg:
        openai_cfg["models"] = []

    OPENCLAW_CONFIG.write_text(json.dumps(data, indent=2) + "\n")

    # Write API key to auth-profiles.json (where OpenClaw gateway reads it)
    if api_key and OPENCLAW_AUTH_PROFILES.exists():
        auth_data = json.loads(OPENCLAW_AUTH_PROFILES.read_text())
        profile = auth_data.setdefault("profiles", {}).setdefault("openai:default", {})
        # Backup original key for deactivation restore
        if not profile.get("_original_key") and profile.get("key"):
            profile["_original_key"] = profile["key"]
        profile["key"] = api_key
        profile["type"] = "api_key"
        profile["provider"] = "openai"
        OPENCLAW_AUTH_PROFILES.write_text(json.dumps(auth_data, indent=2) + "\n")

    detail = f"Set models.providers.openai.baseUrl → {proxy_url}/openai/v1"
    if api_key:
        detail += f", auth-profiles key → {api_key[:16]}…"
    return {"ok": True, "detail": detail}


def _remove_openclaw() -> dict:
    """
    Remove proxy baseUrl from models.providers in ~/.openclaw/openclaw.json
    and restore original API key in auth-profiles.json.
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

        # Remove proxy baseUrl
        if "baseUrl" in prov_cfg:
            del prov_cfg["baseUrl"]
            changed = True

        # Clean up legacy fields
        prov_cfg.pop("apiKey", None)
        prov_cfg.pop("_original_apiKey", None)

    OPENCLAW_CONFIG.write_text(json.dumps(data, indent=2) + "\n")

    # Restore original API key in auth-profiles.json
    if OPENCLAW_AUTH_PROFILES.exists():
        auth_data = json.loads(OPENCLAW_AUTH_PROFILES.read_text())
        profile = auth_data.get("profiles", {}).get("openai:default", {})
        original_key = profile.pop("_original_key", None)
        if original_key:
            profile["key"] = original_key
            changed = True
        OPENCLAW_AUTH_PROFILES.write_text(json.dumps(auth_data, indent=2) + "\n")

    detail = "Removed proxy config from providers" if changed else "No proxy config found"
    return {"ok": True, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class ActivateRequest(BaseModel):
    """Optional API key to write into the tool's config."""
    api_key: str = ""


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
    Activate Claude Code CLI: set ANTHROPIC_BASE_URL and optionally
    ANTHROPIC_API_KEY in ~/.claude/settings.json.
    """
    proxy_base = _proxy_base_url()
    api_key = body.api_key if body else None
    try:
        result = _write_claude_code(proxy_base, api_key=api_key or None)
        logger.info("Claude Code activated%s", " (with API key)" if api_key else " (proxy URL only)")
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
    Activate OpenClaw: set provider baseUrl and optionally apiKey.
    """
    proxy_base = _proxy_base_url()
    api_key = body.api_key if body else None
    try:
        result = _write_openclaw(proxy_base, api_key=api_key or None)
        logger.info("OpenClaw activated%s", " (with API key)" if api_key else " (proxy URL only)")
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
