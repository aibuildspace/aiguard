import asyncio
import json
import os
from pathlib import Path

import typer
from aigate.cli.theme import console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

app = typer.Typer(help="Manage users and API keys", no_args_is_help=True)


@app.command("create")
def create_user(
    email: str = typer.Option(..., "--email", "-e"),
    org: str = typer.Option(..., "--org", "-o", help="Org slug"),
    name: str = typer.Option("", "--name", "-n"),
    role: str = typer.Option("member", "--role", help="admin | member | readonly"),
):
    """Create a user in an organisation."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org
        from aigate.db.models.user import User
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        async with async_session_factory() as session:
            result = await session.execute(select(Org).where(Org.slug == org))
            org_obj = result.scalar_one_or_none()
            if not org_obj:
                console.print(f"[error]Org '{org}' not found[/error]")
                raise typer.Exit(1)

            user = User(org_id=org_obj.id, email=email, name=name or email, role=role)
            try:
                session.add(user)
                await session.commit()
                await session.refresh(user)
            except IntegrityError:
                console.print(f"[warn]User '{email}' already exists[/warn]")
                return
        console.print(f"[success]✓ Created user[/success] {email} (id: {user.id})")

    asyncio.run(_run())


@app.command("list")
def list_users(org: str = typer.Option(None, "--org", "-o", help="Filter by org slug")):
    """List users."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.user import User
        from aigate.db.models.org import Org
        from sqlalchemy import select

        async with async_session_factory() as session:
            q = select(User)
            if org:
                result = await session.execute(select(Org).where(Org.slug == org))
                org_obj = result.scalar_one_or_none()
                if org_obj:
                    q = q.where(User.org_id == org_obj.id)
            result = await session.execute(q)
            users = result.scalars().all()

        table = Table("ID", "Email", "Name", "Role", "Active")
        for u in users:
            table.add_row(
                str(u.id)[:8] + "...",
                u.email,
                u.name,
                u.role,
                "[success]✓[/success]" if u.is_active else "[error]✗[/error]",
            )
        console.print(table)

    asyncio.run(_run())


@app.command("key")
def create_key(
    email: str = typer.Argument(..., help="User email"),
    label: str = typer.Option("default", "--label", "-l"),
    provider: str = typer.Option("any", "--provider", "-p", help="anthropic | openai | any"),
    upstream_key: str = typer.Option(None, "--upstream-key", "-u", help="Upstream API key to store (key-vault mode)"),
):
    """Generate an API key for a user."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.user import User
        from aigate.db.models.api_key import ApiKey
        from aigate.proxy.middleware import generate_api_key
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                console.print(f"[error]User '{email}' not found[/error]")
                raise typer.Exit(1)

            full_key, key_prefix, key_hash = generate_api_key(str(user.org_id)[:8])

            upstream_encrypted = None
            if upstream_key:
                from aigate.crypto import encrypt
                upstream_encrypted = encrypt(upstream_key)

            api_key = ApiKey(
                org_id=user.org_id,
                user_id=user.id,
                key_prefix=key_prefix,
                key_hash=key_hash,
                label=label,
                provider=provider,
                upstream_key_encrypted=upstream_encrypted,
            )
            session.add(api_key)
            await session.commit()

        console.print(f"\n[bold success]API Key created[/bold success]")
        console.print(f"[warn]Save this key — it won't be shown again:[/warn]")
        console.print(f"\n  [bold accent]{full_key}[/bold accent]\n")
        console.print(f"Configure your tool:")
        console.print(f"  ANTHROPIC_BASE_URL=http://127.0.0.1:8080/anthropic")
        console.print(f"  ANTHROPIC_API_KEY={full_key}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Helper: generate tool config snippets
# ---------------------------------------------------------------------------

def _tool_configs(key: str, host: str, port: int, provider: str) -> dict[str, dict]:
    """Return config snippets for each supported AI tool."""
    base = f"http://{host}:{port}"
    configs = {}

    # Claude Code (CLI)
    configs["Claude Code"] = {
        "description": "Set these environment variables in your shell profile (~/.zshrc, ~/.bashrc):",
        "env": {
            "ANTHROPIC_BASE_URL": f"{base}/anthropic",
            "ANTHROPIC_API_KEY": key,
        },
        "file_hint": "Add to ~/.zshrc or ~/.bashrc, then run: source ~/.zshrc",
        "format": "shell",
    }

    # Cursor
    configs["Cursor"] = {
        "description": "Add to Cursor settings (Settings → Models → OpenAI API Base URL):",
        "json_config": {
            "openai.apiBaseUrl": f"{base}/openai/v1",
            "openai.apiKey": key,
        },
        "file_hint": "Open Cursor → Settings → search 'OpenAI' → paste the base URL and key",
        "format": "json",
    }

    # Continue (VS Code extension)
    configs["Continue"] = {
        "description": "Add to ~/.continue/config.json:",
        "json_config": {
            "models": [
                {
                    "title": "AIGate Proxy",
                    "provider": "openai" if provider in ("openai", "any") else provider,
                    "model": "gpt-4",
                    "apiBase": f"{base}/openai/v1" if provider in ("openai", "any") else f"{base}/{provider}",
                    "apiKey": key,
                }
            ]
        },
        "file_hint": "Edit ~/.continue/config.json",
        "format": "json",
    }

    # OpenClaw / generic OpenAI-compatible
    configs["OpenAI / OpenClaw"] = {
        "description": "Set these environment variables:",
        "env": {
            "OPENAI_BASE_URL": f"{base}/openai/v1",
            "OPENAI_API_KEY": key,
        },
        "file_hint": "Add to ~/.zshrc or ~/.bashrc, then run: source ~/.zshrc",
        "format": "shell",
    }

    # Anthropic SDK
    configs["Anthropic SDK"] = {
        "description": "Set these environment variables:",
        "env": {
            "ANTHROPIC_BASE_URL": f"{base}/anthropic",
            "ANTHROPIC_API_KEY": key,
        },
        "file_hint": "Add to ~/.zshrc or ~/.bashrc, then run: source ~/.zshrc",
        "format": "shell",
    }

    return configs


def _print_tool_config(tool_name: str, cfg: dict):
    """Pretty-print a single tool configuration."""
    console.print(f"\n[bold accent]{tool_name}[/bold accent]")
    console.print(f"  {cfg['description']}")
    console.print(f"  [muted]{cfg['file_hint']}[/muted]\n")

    if "env" in cfg:
        lines = "\n".join(f'export {k}="{v}"' for k, v in cfg["env"].items())
        console.print(Syntax(lines, "bash", theme="monokai", padding=1))
    elif "json_config" in cfg:
        formatted = json.dumps(cfg["json_config"], indent=2)
        console.print(Syntax(formatted, "json", theme="monokai", padding=1))


@app.command("setup")
def setup_user(
    email: str = typer.Option(None, "--email", "-e", help="User email"),
    org: str = typer.Option(None, "--org", "-o", help="Org slug (created if it doesn't exist)"),
    name: str = typer.Option("", "--name", "-n", help="User display name"),
    provider: str = typer.Option(None, "--provider", "-p", help="anthropic | openai | any"),
    upstream_key: str = typer.Option(None, "--upstream-key", "-u", help="Upstream API key (key-vault mode)"),
    tool: str = typer.Option(None, "--tool", "-t", help="Output config for: claude | cursor | continue | openai | all"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Interactive prompts"),
):
    """One-command setup: create org + user + key, output tool config.

    \b
    Examples:
        aigate user setup
        aigate user setup --email alice@co.com --org acme --provider anthropic --tool claude
        aigate user setup --no-interactive --email bob@co.com --org acme --provider openai --tool all
    """
    import questionary

    from aigate.config import settings

    # Interactive prompts for missing values
    if interactive:
        if not org:
            org = questionary.text(
                "Organisation slug:",
                default="default",
                instruction="(lowercase, hyphens ok)",
            ).ask()
            if not org:
                raise typer.Abort()

        if not email:
            email = questionary.text(
                "User email:",
                instruction="(used as the user identifier)",
            ).ask()
            if not email:
                raise typer.Abort()

        if not name:
            name = questionary.text(
                "Display name:",
                default=email.split("@")[0] if email else "",
            ).ask() or ""

        if not provider:
            provider = questionary.select(
                "Which LLM provider?",
                choices=[
                    questionary.Choice("Anthropic (Claude)", value="anthropic"),
                    questionary.Choice("OpenAI (GPT)", value="openai"),
                    questionary.Choice("Any / both", value="any"),
                ],
                default="anthropic",
            ).ask()
            if not provider:
                raise typer.Abort()

        if not tool:
            tool_map = {
                "Claude Code": "claude",
                "Cursor": "cursor",
                "Continue (VS Code)": "continue",
                "OpenAI / OpenClaw": "openai",
                "All tools": "all",
            }
            selected = questionary.select(
                "Which AI tool are you configuring?",
                choices=list(tool_map.keys()),
            ).ask()
            if not selected:
                raise typer.Abort()
            tool = tool_map[selected]
    else:
        # Non-interactive defaults
        org = org or "default"
        email = email or ""
        provider = provider or "any"
        tool = tool or "all"
        if not email:
            console.print("[error]--email is required in non-interactive mode[/error]")
            raise typer.Exit(1)

    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org
        from aigate.db.models.user import User
        from aigate.db.models.api_key import ApiKey
        from aigate.proxy.middleware import generate_api_key
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError
        import re

        async with async_session_factory() as session:
            # 1. Ensure org exists
            result = await session.execute(select(Org).where(Org.slug == org))
            org_obj = result.scalar_one_or_none()
            if not org_obj:
                slug = re.sub(r"[^a-z0-9]+", "-", org.lower()).strip("-")[:32]
                org_obj = Org(name=org.replace("-", " ").title(), slug=slug)
                session.add(org_obj)
                try:
                    await session.commit()
                    await session.refresh(org_obj)
                    console.print(f"[success]✓ Created org[/success] [bold]{org_obj.name}[/bold] (slug: {org_obj.slug})")
                except IntegrityError:
                    await session.rollback()
                    result = await session.execute(select(Org).where(Org.slug == org))
                    org_obj = result.scalar_one_or_none()
            else:
                console.print(f"[muted]Org '{org}' already exists[/muted]")

            # 2. Ensure user exists
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = User(org_id=org_obj.id, email=email, name=name or email, role="admin")
                session.add(user)
                try:
                    await session.commit()
                    await session.refresh(user)
                    console.print(f"[success]✓ Created user[/success] {email}")
                except IntegrityError:
                    await session.rollback()
                    result = await session.execute(select(User).where(User.email == email))
                    user = result.scalar_one_or_none()
            else:
                console.print(f"[muted]User '{email}' already exists[/muted]")

            # 3. Generate API key
            full_key, key_prefix, key_hash = generate_api_key(org_obj.slug[:8])

            upstream_encrypted = None
            if upstream_key:
                from aigate.crypto import encrypt
                upstream_encrypted = encrypt(upstream_key)

            api_key = ApiKey(
                org_id=org_obj.id,
                user_id=user.id,
                key_prefix=key_prefix,
                key_hash=key_hash,
                label=f"{provider}-key",
                provider=provider,
                upstream_key_encrypted=upstream_encrypted,
            )
            session.add(api_key)
            await session.commit()

        return full_key

    full_key = asyncio.run(_run())

    # Print the key
    console.print()
    console.print(Panel(
        f"[bold accent]{full_key}[/bold accent]",
        title="[warn]Your API Key (save it — shown only once)[/warn]",
        border_style="success",
    ))

    # Print tool configuration
    host = settings.host
    port = settings.port
    configs = _tool_configs(full_key, host, port, provider)

    tool_lower = (tool or "all").lower()
    tool_name_map = {
        "claude": "Claude Code",
        "cursor": "Cursor",
        "continue": "Continue",
        "openai": "OpenAI / OpenClaw",
        "openclaw": "OpenAI / OpenClaw",
        "anthropic": "Anthropic SDK",
        "all": None,
    }

    console.print(f"\n[bold]Configuration for your AI tool:[/bold]")

    if tool_lower == "all":
        for tname, cfg in configs.items():
            _print_tool_config(tname, cfg)
    else:
        target = tool_name_map.get(tool_lower)
        if target and target in configs:
            _print_tool_config(target, configs[target])
        else:
            console.print(f"[warn]Unknown tool '{tool}', showing all configs:[/warn]")
            for tname, cfg in configs.items():
                _print_tool_config(tname, cfg)

    console.print()


@app.command("config")
def show_config(
    email: str = typer.Argument(..., help="User email"),
    tool: str = typer.Option("all", "--tool", "-t", help="claude | cursor | continue | openai | all"),
):
    """Show connection config for a user's existing API key."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.user import User
        from aigate.db.models.api_key import ApiKey
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                console.print(f"[error]User '{email}' not found[/error]")
                raise typer.Exit(1)

            result = await session.execute(
                select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.key_prefix)
            )
            keys = result.scalars().all()
            if not keys:
                console.print(f"[warn]No API keys found for {email}. Run: aigate user setup[/warn]")
                raise typer.Exit(1)

            return keys[0].key_prefix, keys[0].provider

    key_prefix, provider = asyncio.run(_run())

    from aigate.config import settings
    console.print(f"\n[bold]Config for {email}[/bold] (key prefix: {key_prefix}...)")
    console.print("[muted]Note: full key is not stored. Use 'aigate user setup' to generate a new one.[/muted]")

    configs = _tool_configs(f"{key_prefix}...<your-key>", settings.host, settings.port, provider or "any")

    tool_lower = tool.lower()
    tool_name_map = {
        "claude": "Claude Code",
        "cursor": "Cursor",
        "continue": "Continue",
        "openai": "OpenAI / OpenClaw",
        "openclaw": "OpenAI / OpenClaw",
        "anthropic": "Anthropic SDK",
        "all": None,
    }

    if tool_lower == "all":
        for tname, cfg in configs.items():
            _print_tool_config(tname, cfg)
    else:
        target = tool_name_map.get(tool_lower)
        if target and target in configs:
            _print_tool_config(target, configs[target])
        else:
            for tname, cfg in configs.items():
                _print_tool_config(tname, cfg)
