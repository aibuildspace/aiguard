"""guard setup — configure AI coding tools to use the AIGuard proxy."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import questionary
import typer
from rich.panel import Panel
from rich.table import Table

from aiguard.cli.theme import console, PROMPT_STYLE

app = typer.Typer(no_args_is_help=True)

_style = PROMPT_STYLE

OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
OPENCLAW_AUTH_PROFILES = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

# ── helpers ──────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _set_nested(obj: dict, dotpath: str, value):
    """Set a value in a nested dict using dot-separated path."""
    keys = dotpath.split(".")
    for key in keys[:-1]:
        obj = obj.setdefault(key, {})
    obj[keys[-1]] = value


def _get_nested(obj: dict, dotpath: str, default=None):
    """Get a value from a nested dict using dot-separated path."""
    for key in dotpath.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            return default
    return obj


# ── OpenClaw ─────────────────────────────────────────────────────────────────


def _configure_openclaw(proxy_url: str, api_key: str) -> bool:
    """Configure OpenClaw to route through AIGuard."""
    base_url = proxy_url.rstrip("/") + "/openai/v1"

    # Write baseUrl to openclaw.json (merge into existing config)
    data = _read_json(OPENCLAW_CONFIG)  # returns {} if file doesn't exist
    openai_cfg = data.setdefault("models", {}).setdefault("providers", {}).setdefault("openai", {})
    openai_cfg["baseUrl"] = base_url
    openai_cfg.setdefault("models", [])  # OpenClaw requires this array
    _write_json(OPENCLAW_CONFIG, data)  # creates parent dirs if needed

    # Write API key to auth-profiles.json (where gateway reads it)
    if OPENCLAW_AUTH_PROFILES.exists():
        auth_data = _read_json(OPENCLAW_AUTH_PROFILES)
        profiles = auth_data.setdefault("profiles", {})
        profile = profiles.setdefault("openai:default", {})
        # Backup original key for reset (skip if already a proxy key)
        existing = profile.get("key", "")
        if not profile.get("_original_key") and existing and not existing.startswith("aip_"):
            profile["_original_key"] = existing
        profile["key"] = api_key
        profile["type"] = "api_key"
        profile["provider"] = "openai"
        _write_json(OPENCLAW_AUTH_PROFILES, auth_data)
        console.print(f"  [success]\u2713[/success] OpenClaw configured \u2192 {OPENCLAW_CONFIG} + auth-profiles.json")
    else:
        console.print(f"  [success]\u2713[/success] OpenClaw configured \u2192 {OPENCLAW_CONFIG}")
        console.print("  [warning]\u26a0[/warning]  auth-profiles.json not found \u2014 run [accent]openclaw onboard[/accent] first")

    # Auto-restart gateway
    _restart_openclaw()

    return True


def _restart_openclaw() -> None:
    """Restart the OpenClaw gateway, or start it if not running."""
    if not shutil.which("openclaw"):
        console.print("  [dim]Run [accent]openclaw gateway start[/accent] to apply changes[/dim]")
        return

    def _run_openclaw(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
        """Run openclaw via login shell so nvm/fnm PATH is inherited."""
        cmd = " ".join(args)
        return subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True, text=True, timeout=timeout,
        )

    def _check_node_error(result: subprocess.CompletedProcess) -> bool:
        """If openclaw failed due to Node version, print helpful guidance."""
        output = (result.stdout or "") + (result.stderr or "")
        if "Node.js" in output and "required" in output:
            console.print("  [warning]⚠  OpenClaw requires Node.js v22+[/warning]")
            console.print("  [dim]Run: nvm install 22 && nvm alias default 22[/dim]")
            return True
        return False

    try:
        # Check if gateway is running
        result = _run_openclaw(["openclaw", "gateway", "status"], timeout=5)
        if result.returncode != 0:
            if _check_node_error(result):
                # openclaw CLI won't work, but gateway may be running
                # Kill it so TUI respawns with fresh config
                _kill_openclaw_gateway()
                return
            # Not running — try to start it
            start_result = _run_openclaw(["openclaw", "gateway", "start"])
            if start_result.returncode == 0:
                console.print("  [success]✓[/success] OpenClaw gateway started")
            elif not _check_node_error(start_result):
                console.print("  [dim]Run [accent]openclaw gateway start[/accent] to apply changes[/dim]")
            return
        # Running — restart it
        restart_result = _run_openclaw(["openclaw", "gateway", "restart"])
        if restart_result.returncode == 0:
            console.print("  [success]✓[/success] OpenClaw gateway restarted")
        elif not _check_node_error(restart_result):
            # Fallback: kill the gateway process so TUI respawns it
            _kill_openclaw_gateway()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        _kill_openclaw_gateway()


def _kill_openclaw_gateway() -> None:
    """Kill the openclaw-gateway process so the TUI respawns it with fresh config."""
    try:
        result = subprocess.run(
            ["pkill", "-f", "openclaw-gateway"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            console.print("  [success]✓[/success] OpenClaw gateway stopped — TUI will restart it automatically")
        else:
            console.print("  [warning]⚠[/warning]  Kill the OpenClaw TUI and re-open it to apply changes")
    except Exception:
        console.print("  [warning]⚠[/warning]  Kill the OpenClaw TUI and re-open it to apply changes")


def _show_openclaw_status() -> None:
    """Show current OpenClaw proxy config."""
    if not OPENCLAW_CONFIG.exists():
        console.print("  [muted]not installed[/muted]")
        return
    data = _read_json(OPENCLAW_CONFIG)
    url = _get_nested(data, "models.providers.openai.baseUrl", "[muted]not set[/muted]")
    console.print(f"  Base URL : [value]{url}[/value]")

    # Read actual key from auth-profiles.json
    key = None
    if OPENCLAW_AUTH_PROFILES.exists():
        auth_data = _read_json(OPENCLAW_AUTH_PROFILES)
        key = auth_data.get("profiles", {}).get("openai:default", {}).get("key")
    key_display = f"{key[:16]}…" if key and len(key) > 16 else (key or "[muted]not set[/muted]")
    console.print(f"  API Key  : [value]{key_display}[/value]")


# ── Claude Code ──────────────────────────────────────────────────────────────


def _configure_claude(proxy_url: str, api_key: str) -> bool:
    """Configure Claude Code to route through AIGuard."""
    base_url = proxy_url.rstrip("/") + "/anthropic"

    data = _read_json(CLAUDE_SETTINGS)
    env = data.setdefault("env", {})
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_API_KEY"] = api_key
    _write_json(CLAUDE_SETTINGS, data)
    console.print("  [success]✓[/success] Claude Code configured")
    console.print("  [muted]Restart Claude Code for changes to take effect[/muted]")
    return True


def _show_claude_status() -> None:
    """Show current Claude Code proxy config."""
    if not CLAUDE_SETTINGS.exists():
        console.print("  [muted]not installed[/muted]")
        return
    data = _read_json(CLAUDE_SETTINGS)
    env = data.get("env", {})
    url = env.get("ANTHROPIC_BASE_URL", "[muted]not set[/muted]")
    key = env.get("ANTHROPIC_API_KEY")
    key_display = f"{key[:16]}…" if key and len(key) > 16 else (key or "[muted]not set[/muted]")
    console.print(f"  Base URL : [value]{url}[/value]")
    console.print(f"  API Key  : [value]{key_display}[/value]")


# ── Commands ─────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def setup_interactive(
    ctx: typer.Context,
    url: str = typer.Option(None, "--url", "-u", help="AIGuard proxy URL"),
    key: str = typer.Option(None, "--key", "-k", help="AIGuard API key"),
):
    """Configure AI coding tools to use the AIGuard proxy."""
    if ctx.invoked_subcommand is not None:
        return

    console.print(Panel(
        "[bold]Configure your AI coding tools to route through AIGuard[/bold]",
        title="[accent]guard setup[/accent]",
        border_style="accent",
    ))

    # Detect which tools are available
    tools_available = []
    if OPENCLAW_CONFIG.exists() or shutil.which("openclaw"):
        tools_available.append("OpenClaw")
    if CLAUDE_SETTINGS.exists():
        tools_available.append("Claude Code")

    if not tools_available:
        console.print("[warn]No supported AI tools detected.[/warn]")
        console.print("  Looked for:")
        console.print(f"    • OpenClaw  → {OPENCLAW_CONFIG}")
        console.print(f"    • Claude Code → {CLAUDE_SETTINGS}")
        raise typer.Exit(1)

    # Pick tools to configure
    if len(tools_available) == 1:
        selected = tools_available
        console.print(f"  Detected: [accent]{selected[0]}[/accent]")
    else:
        selected = questionary.checkbox(
            "Which tools to configure?",
            choices=tools_available,
            default=tools_available,
            style=_style,
        ).ask()
        if not selected:
            raise typer.Abort()

    # Proxy URL
    if not url:
        console.print()
        url = questionary.text(
            "AIGuard proxy URL:",
            default="http://localhost:8080",
            style=_style,
        ).ask()
    if not url:
        raise typer.Abort()

    # API Key
    if not key:
        key = questionary.password(
            "AIGuard API key (aip_...):",
            style=_style,
        ).ask()
    if not key:
        raise typer.Abort()

    console.print()

    # Apply
    for tool in selected:
        if tool == "OpenClaw":
            _configure_openclaw(url, key)
        elif tool == "Claude Code":
            _configure_claude(url, key)

    # Summary
    console.print()
    console.print(Panel(
        "[success]Done![/success] Your AI tools will now route through AIGuard.\n"
        "Restart any running tool for changes to take effect.",
        border_style="success",
    ))


@app.command("openclaw")
def setup_openclaw(
    url: str = typer.Option(None, "--url", "-u", help="AIGuard proxy URL"),
    key: str = typer.Option(None, "--key", "-k", help="AIGuard API key"),
    default: bool = typer.Option(False, "--default", "-d", help="Reset to default (remove proxy)"),
):
    """Configure OpenClaw to route through AIGuard, or reset to defaults."""
    if default:
        _reset_openclaw()
        return
    if not url:
        url = questionary.text(
            "AIGuard proxy URL:",
            default="http://localhost:8080",
            style=_style,
        ).ask()
    if not key:
        key = questionary.password("AIGuard API key (aip_...):", style=_style).ask()
    if not url or not key:
        raise typer.Abort()

    console.print()
    _configure_openclaw(url, key)


@app.command("claude")
def setup_claude(
    url: str = typer.Option(None, "--url", "-u", help="AIGuard proxy URL"),
    key: str = typer.Option(None, "--key", "-k", help="AIGuard API key"),
    default: bool = typer.Option(False, "--default", "-d", help="Reset to default (remove proxy)"),
):
    """Configure Claude Code to route through AIGuard, or reset to defaults."""
    if default:
        _reset_claude()
        return
    if not url:
        url = questionary.text(
            "AIGuard proxy URL:",
            default="http://localhost:8080",
            style=_style,
        ).ask()
    if not key:
        key = questionary.password("AIGuard API key (aip_...):", style=_style).ask()
    if not url or not key:
        raise typer.Abort()

    console.print()
    _configure_claude(url, key)


@app.command("status")
def setup_status():
    """Show current proxy configuration for all detected tools."""
    console.print(Panel(
        "[bold]Current AIGuard proxy configuration[/bold]",
        title="[accent]guard setup status[/accent]",
        border_style="accent",
    ))

    console.print("[accent]OpenClaw[/accent]")
    _show_openclaw_status()
    console.print()
    console.print("[accent]Claude Code[/accent]")
    _show_claude_status()


@app.command("reset")
def setup_reset():
    """Remove AIGuard proxy configuration from all tools."""
    confirm = questionary.confirm(
        "Remove AIGuard proxy config from all tools?",
        default=False,
        style=_style,
    ).ask()
    if not confirm:
        raise typer.Abort()

    # OpenClaw — remove baseUrl and restore original key
    if OPENCLAW_CONFIG.exists():
        if shutil.which("openclaw"):
            try:
                subprocess.run(
                    ["openclaw", "config", "unset", "models.providers.openai.baseUrl"],
                    check=True, capture_output=True, text=True,
                )
                console.print("  [success]✓[/success] OpenClaw proxy config removed")
            except subprocess.CalledProcessError:
                data = _read_json(OPENCLAW_CONFIG)
                providers = _get_nested(data, "models.providers.openai", {})
                if isinstance(providers, dict):
                    providers.pop("baseUrl", None)
                    providers.pop("apiKey", None)
                    _write_json(OPENCLAW_CONFIG, data)
                    console.print("  [success]✓[/success] OpenClaw proxy config removed (file edit)")
        else:
            data = _read_json(OPENCLAW_CONFIG)
            providers = _get_nested(data, "models.providers.openai", {})
            if isinstance(providers, dict):
                providers.pop("baseUrl", None)
                providers.pop("apiKey", None)
                _write_json(OPENCLAW_CONFIG, data)
                console.print("  [success]✓[/success] OpenClaw proxy config removed")

        # Restore original API key in auth-profiles.json
        if OPENCLAW_AUTH_PROFILES.exists():
            auth_data = _read_json(OPENCLAW_AUTH_PROFILES)
            profile = auth_data.get("profiles", {}).get("openai:default", {})
            original_key = profile.pop("_original_key", None)
            if original_key:
                profile["key"] = original_key
                _write_json(OPENCLAW_AUTH_PROFILES, auth_data)
                console.print("  [success]✓[/success] OpenClaw original API key restored")

    # Claude Code — remove env vars
    if CLAUDE_SETTINGS.exists():
        data = _read_json(CLAUDE_SETTINGS)
        env = data.get("env", {})
        env.pop("ANTHROPIC_BASE_URL", None)
        env.pop("ANTHROPIC_API_KEY", None)
        _write_json(CLAUDE_SETTINGS, data)
        console.print("  [success]✓[/success] Claude Code proxy config removed")
