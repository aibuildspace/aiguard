import typer

app = typer.Typer(
    name="aiguard",
    help="AIGuard — anti-virus for AI. Security middleware proxy for LLM APIs.",
    no_args_is_help=True,
)

from aiguard.cli.commands.server import app as server_app
from aiguard.cli.commands.org import app as org_app
from aiguard.cli.commands.user import app as user_app
from aiguard.cli.commands.shield import app as shield_app
from aiguard.cli.commands.audit import app as audit_app
from aiguard.cli.commands.onboard import onboard as onboard_cmd

app.add_typer(server_app, name="server", help="Server management (start, stop, status)")
app.add_typer(org_app, name="org", help="Manage organisations")
app.add_typer(user_app, name="user", help="Manage users and API keys")
app.add_typer(shield_app, name="shield", help="Manage and test shields")
app.add_typer(audit_app, name="audit", help="View audit logs")

app.command("onboard")(onboard_cmd)


def _ensure_env_key(env_var: str, generator, console, *, label: str) -> str | None:
    """
    If *env_var* is missing from both the environment and .env,
    generate a value, persist it to .env, set it in os.environ,
    and inform the user.  Returns the (possibly generated) value.
    """
    import os
    from pathlib import Path

    current = os.environ.get(env_var, "").strip()
    if current:
        return current

    # Also check .env in case pydantic-settings hasn't loaded it yet
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith(f"{env_var}="):
                val = line.split("=", 1)[1].strip()
                if val:
                    os.environ[env_var] = val
                    return val

    # Generate
    generated = generator()
    os.environ[env_var] = generated

    # Persist to .env
    if env_path.exists():
        content = env_path.read_text()
        if env_var not in content:
            with env_path.open("a") as f:
                f.write(f"\n{env_var}={generated}\n")
    else:
        env_path.write_text(f"{env_var}={generated}\n")

    console.print(f"[warning]⚠  {label} not set — generated and saved to .env[/warning]")
    return generated


def _start_server(
    *,
    mode: str,
    host: str,
    port: int,
    workers: int,
    reload: bool,
) -> None:
    """Internal helper to start uvicorn with the given mode."""
    import os
    import secrets
    import uvicorn
    from cryptography.fernet import Fernet
    from aiguard.cli.theme import console

    # Set mode before the app module is imported by uvicorn
    os.environ["GUARD_MODE"] = mode

    mode_label = "[bold red]PROD[/bold red] (locked-down)" if mode == "prod" else "[bold green]DEV[/bold green] (full access)"
    console.print(f"[bold success]AIGuard[/bold success] starting in {mode_label} on [accent]http://{host}:{port}[/accent]")

    # ── Auto-generate secrets if missing (both modes) ─────────────────────
    admin_key = _ensure_env_key(
        "GUARD_ADMIN_API_KEY",
        lambda: f"guard_{secrets.token_urlsafe(32)}",
        console,
        label="GUARD_ADMIN_API_KEY",
    )
    _ensure_env_key(
        "GUARD_ENCRYPTION_KEY",
        lambda: Fernet.generate_key().decode(),
        console,
        label="GUARD_ENCRYPTION_KEY",
    )

    if mode == "prod":
        console.print("  [dim]Portal: disabled  |  Admin API: read-only  |  CORS: restricted[/dim]")
        console.print(f"  [dim]Admin Key: {admin_key}[/dim]")
        if reload:
            console.print("  [warning]⚠  --reload is ignored in prod mode[/warning]")
            reload = False

    uvicorn.run(
        "aiguard.main:app",
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
        log_level="info",
    )


@app.command("start")
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(1, "--workers", "-w", help="Uvicorn worker count"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev only)"),
    mode: str = typer.Option("dev", "--mode", "-m", help="Run mode: dev or prod"),
):
    """Start the AIGuard server (default: dev mode)."""
    if mode not in ("dev", "prod"):
        from aiguard.cli.theme import console
        console.print(f"[error]Invalid mode '{mode}'. Use 'dev' or 'prod'.[/error]")
        raise typer.Exit(1)
    _start_server(mode=mode, host=host, port=port, workers=workers, reload=reload)


@app.command("startdev")
def startdev(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(1, "--workers", "-w", help="Uvicorn worker count"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start AIGuard in DEV mode — full access, portal enabled."""
    _start_server(mode="dev", host=host, port=port, workers=workers, reload=reload)


@app.command("startprod")
def startprod(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    workers: int = typer.Option(4, "--workers", "-w", help="Uvicorn worker count"),
):
    """Start AIGuard in PROD mode — locked-down, read-only admin API, no portal."""
    _start_server(mode="prod", host=host, port=port, workers=workers, reload=False)


@app.command("config")
def show_config():
    """Show resolved configuration."""
    import json
    from rich.syntax import Syntax
    from aiguard.cli.theme import console
    from aiguard.config import settings
    data = settings.model_dump()
    # Redact sensitive values
    for key in ("encryption_key", "admin_api_key"):
        if data.get(key):
            data[key] = "***"
    console.print(Syntax(json.dumps(data, indent=2), "json"))


if __name__ == "__main__":
    app()
