"""Interactive onboarding wizard: Org → User → API Key."""
import asyncio

import questionary
import typer
from aigate.cli.theme import console, PROMPT_STYLE
from rich.panel import Panel
from rich.table import Table

# ── Questionary styling (from theme) ───────────────────────────────
_style = PROMPT_STYLE

CREATE_NEW = "✚  Create new"
GO_BACK = "←  Back"

# Sentinel returned by pickers to signal "go back"
_BACK = object()


# ── DB helpers (async) ───────────────────────────────────────────────────

async def _ensure_db():
    from aigate.db.engine import init_db
    await init_db()


async def _fetch_orgs():
    from aigate.db.engine import async_session_factory
    from aigate.db.models.org import Org
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(select(Org).order_by(Org.name))
        return result.scalars().all()


async def _create_org(name: str, slug: str):
    from aigate.db.engine import async_session_factory
    from aigate.db.models.org import Org
    from sqlalchemy.exc import IntegrityError

    org = Org(name=name, slug=slug)
    async with async_session_factory() as session:
        session.add(org)
        try:
            await session.commit()
            await session.refresh(org)
            return org
        except IntegrityError:
            await session.rollback()
            from sqlalchemy import select
            result = await session.execute(select(Org).where(Org.slug == slug))
            return result.scalar_one_or_none()


async def _fetch_users(org_id):
    from aigate.db.engine import async_session_factory
    from aigate.db.models.user import User
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.org_id == org_id).order_by(User.email)
        )
        return result.scalars().all()


async def _create_user(org_id, email: str, name: str, role: str = "member"):
    from aigate.db.engine import async_session_factory
    from aigate.db.models.user import User
    from sqlalchemy.exc import IntegrityError

    user = User(org_id=org_id, email=email, name=name, role=role)
    async with async_session_factory() as session:
        session.add(user)
        try:
            await session.commit()
            await session.refresh(user)
            return user
        except IntegrityError:
            await session.rollback()
            from sqlalchemy import select
            result = await session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()


async def _fetch_keys(user_id):
    from aigate.db.engine import async_session_factory
    from aigate.db.models.api_key import ApiKey
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at)
        )
        return result.scalars().all()


async def _create_key(org_id, user_id, org_slug: str, label: str, provider: str, upstream_key: str | None = None):
    from aigate.db.engine import async_session_factory
    from aigate.db.models.api_key import ApiKey
    from aigate.proxy.middleware import generate_api_key

    full_key, key_prefix, key_hash = generate_api_key(org_slug[:8])

    upstream_encrypted = None
    if upstream_key:
        from aigate.crypto import encrypt
        upstream_encrypted = encrypt(upstream_key)

    api_key = ApiKey(
        org_id=org_id,
        user_id=user_id,
        key_prefix=key_prefix,
        key_hash=key_hash,
        label=label,
        provider=provider,
        upstream_key_encrypted=upstream_encrypted,
    )
    async with async_session_factory() as session:
        session.add(api_key)
        await session.commit()
    return full_key, key_prefix


# ── Interactive steps ────────────────────────────────────────────────────

def _pick_org(orgs):
    """Returns (org_obj, is_new) or _BACK."""
    if orgs:
        choices = [
            questionary.Choice(
                title=f"{o.name}  (slug: {o.slug}, {len(o.users)} users)"
                      if hasattr(o, 'users') else f"{o.name}  (slug: {o.slug})",
                value=o,
            )
            for o in orgs
        ]
        choices.append(questionary.Choice(title=CREATE_NEW, value="__create__"))

        selected = questionary.select(
            "Select an organisation:",
            choices=choices,
            style=_style,
        ).ask()

        if selected is None:
            raise typer.Abort()
        if selected != "__create__":
            return selected, False
    else:
        console.print("[muted]No organisations found — let's create one.[/muted]")

    # Create new org
    name = questionary.text(
        "Organisation name:",
        style=_style,
        validate=lambda v: len(v.strip()) > 0 or "Name is required",
    ).ask()
    if not name:
        raise typer.Abort()

    import re
    default_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
    slug = questionary.text(
        "Slug:",
        default=default_slug,
        style=_style,
    ).ask()
    if not slug:
        raise typer.Abort()

    org = asyncio.run(_create_org(name, slug))
    console.print(f"  [success]✓ Created org[/success] [bold]{org.name}[/bold] (slug: {org.slug})")
    return org, True


def _pick_user(org, users):
    """Returns (user_obj, is_new) or _BACK."""
    if users:
        choices = [
            questionary.Choice(
                title=f"{u.email}  ({u.name}, {u.role})",
                value=u,
            )
            for u in users
        ]
        choices.append(questionary.Choice(title=CREATE_NEW, value="__create__"))
        choices.append(questionary.Choice(title=GO_BACK, value="__back__"))

        selected = questionary.select(
            f"Select a user in '{org.name}':",
            choices=choices,
            style=_style,
        ).ask()

        if selected is None:
            raise typer.Abort()
        if selected == "__back__":
            return _BACK
        if selected != "__create__":
            return selected, False
    else:
        console.print(f"[muted]No users in '{org.name}' — let's create one.[/muted]")

    # Create new user
    email = questionary.text(
        "User email:",
        style=_style,
        validate=lambda v: "@" in v or "Enter a valid email",
    ).ask()
    if not email:
        raise typer.Abort()

    default_name = email.split("@")[0]
    name = questionary.text(
        "Display name:",
        default=default_name,
        style=_style,
    ).ask() or default_name

    role = questionary.select(
        "Role:",
        choices=["admin", "member", "readonly"],
        default="member",
        style=_style,
    ).ask()
    if not role:
        raise typer.Abort()

    user = asyncio.run(_create_user(org.id, email, name, role))
    console.print(f"  [success]✓ Created user[/success] {user.email}")
    return user, True


def _pick_key(user, org, keys):
    """Returns (full_key_or_none, key_prefix, provider, is_new) or _BACK."""
    if keys:
        choices = [
            questionary.Choice(
                title=f"{k.key_prefix}…  ({k.label}, provider: {k.provider},"
                      f" {'active' if k.is_active else 'inactive'})",
                value=k,
            )
            for k in keys
        ]
        choices.append(questionary.Choice(title=CREATE_NEW, value="__create__"))
        choices.append(questionary.Choice(title=GO_BACK, value="__back__"))

        selected = questionary.select(
            f"Select an API key for '{user.email}':",
            choices=choices,
            style=_style,
        ).ask()

        if selected is None:
            raise typer.Abort()
        if selected == "__back__":
            return _BACK
        if selected != "__create__":
            return None, selected.key_prefix, selected.provider, False
    else:
        console.print(f"[muted]No API keys for '{user.email}' — let's create one.[/muted]")

    # Create new key
    label = questionary.text(
        "Key label:",
        default="default",
        style=_style,
    ).ask() or "default"

    provider = questionary.select(
        "Provider:",
        choices=[
            questionary.Choice("Anthropic (Claude)", value="anthropic"),
            questionary.Choice("OpenAI (GPT)", value="openai"),
            questionary.Choice("Any / both", value="any"),
        ],
        default="any",
        style=_style,
    ).ask()
    if not provider:
        raise typer.Abort()

    # Ask for the real upstream API key
    provider_label = {"anthropic": "Anthropic", "openai": "OpenAI"}.get(provider, "provider")
    upstream_key = questionary.password(
        f"{provider_label} API key (the real upstream key — stored encrypted):",
        style=_style,
    ).ask()
    if upstream_key is not None:
        upstream_key = upstream_key.strip() or None

    full_key, key_prefix = asyncio.run(_create_key(org.id, user.id, org.slug, label, provider, upstream_key))
    console.print(f"  [success]✓ Created API key[/success] {key_prefix}…")
    return full_key, key_prefix, provider, True


# ── Tool config output (reused from user.py) ────────────────────────────

def _show_tool_config(full_key: str, provider: str):
    """Ask which tool to configure and print the snippet."""
    from aigate.config import settings

    base = f"http://{settings.host}:{settings.port}"

    tool_map = {
        "Claude Code": "claude",
        "Cursor": "cursor",
        "Continue (VS Code)": "continue",
        "OpenAI / OpenClaw": "openai",
        "Anthropic SDK": "anthropic",
        "Skip — I'll configure later": "skip",
    }
    selected = questionary.select(
        "Show config for which AI tool?",
        choices=list(tool_map.keys()),
        style=_style,
    ).ask()
    if not selected:
        return
    tool = tool_map[selected]
    if tool == "skip":
        return

    from rich.syntax import Syntax

    configs = {
        "claude": ("Claude Code", "bash", "\n".join([
            f'export ANTHROPIC_BASE_URL="{base}/anthropic"',
            f'export ANTHROPIC_API_KEY="{full_key}"',
        ]), "Add to ~/.zshrc or ~/.bashrc, then: source ~/.zshrc"),

        "cursor": ("Cursor", "json", _json_str({
            "openai.apiBaseUrl": f"{base}/openai/v1",
            "openai.apiKey": full_key,
        }), "Settings → Models → OpenAI API Base URL"),

        "continue": ("Continue (VS Code)", "json", _json_str({
            "models": [{
                "title": "AIGate Proxy",
                "provider": "openai" if provider in ("openai", "any") else provider,
                "model": "gpt-4",
                "apiBase": f"{base}/openai/v1" if provider in ("openai", "any") else f"{base}/{provider}",
                "apiKey": full_key,
            }]
        }), "Edit ~/.continue/config.json"),

        "openai": ("OpenAI / OpenClaw", "bash", "\n".join([
            f'export OPENAI_BASE_URL="{base}/openai/v1"',
            f'export OPENAI_API_KEY="{full_key}"',
        ]), "Add to ~/.zshrc or ~/.bashrc, then: source ~/.zshrc"),

        "anthropic": ("Anthropic SDK", "bash", "\n".join([
            f'export ANTHROPIC_BASE_URL="{base}/anthropic"',
            f'export ANTHROPIC_API_KEY="{full_key}"',
        ]), "Add to ~/.zshrc or ~/.bashrc, then: source ~/.zshrc"),
    }

    title, lang, code, hint = configs[tool]
    console.print(f"\n[bold accent]{title}[/bold accent]")
    console.print(f"  [muted]{hint}[/muted]\n")
    console.print(Syntax(code, lang, theme="monokai", padding=1))


def _json_str(d: dict) -> str:
    import json
    return json.dumps(d, indent=2)


# ── Main onboard command ────────────────────────────────────────────────

def onboard():
    """Interactive onboarding: Organisation → User → API Key.

    \b
    Walk through selecting or creating an organisation, user, and
    API key in a guided step-by-step flow.  Use ← Back to revisit
    a previous step.
    """
    console.print()
    console.print(
        Panel(
            "[bold]Welcome to AIGate onboarding[/bold]\n"
            "We'll walk you through: [accent]Org → User → API Key[/accent]",
            border_style="accent",
        )
    )

    asyncio.run(_ensure_db())

    # State
    org = user = None
    org_is_new = user_is_new = key_is_new = False
    full_key = key_prefix = provider = None
    step = 1

    while step <= 3:
        # ── Step 1: Organisation ──────────────────────────────────
        if step == 1:
            console.print("\n[bold accent]Step 1 of 3[/bold accent]  [bold]Organisation[/bold]")
            orgs = asyncio.run(_fetch_orgs())
            result = _pick_org(orgs)
            # Step 1 has no previous step so _BACK is not possible
            org, org_is_new = result
            step = 2

        # ── Step 2: User ──────────────────────────────────────────
        elif step == 2:
            console.print(f"\n[bold accent]Step 2 of 3[/bold accent]  [bold]User[/bold]  [muted](org: {org.name})[/muted]")
            users = asyncio.run(_fetch_users(org.id))
            result = _pick_user(org, users)
            if result is _BACK:
                step = 1
                continue
            user, user_is_new = result
            step = 3

        # ── Step 3: API Key ───────────────────────────────────────
        elif step == 3:
            console.print(f"\n[bold accent]Step 3 of 3[/bold accent]  [bold]API Key[/bold]  [muted](user: {user.email})[/muted]")
            keys = asyncio.run(_fetch_keys(user.id))
            result = _pick_key(user, org, keys)
            if result is _BACK:
                step = 2
                continue
            full_key, key_prefix, provider, key_is_new = result
            step = 4  # done

    # Summary
    console.print()
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Organisation", f"{org.name}  [muted](slug: {org.slug})[/muted]"
                     + ("  [success]new[/success]" if org_is_new else ""))
    summary.add_row("User", f"{user.email}  [muted]({user.role})[/muted]"
                     + ("  [success]new[/success]" if user_is_new else ""))
    summary.add_row("API Key", f"{key_prefix}…" + ("  [success]new[/success]" if key_is_new else ""))
    console.print(Panel(summary, title="[bold]Onboarding Summary[/bold]", border_style="success"))

    if full_key:
        # New key — display it prominently
        console.print()
        console.print(Panel(
            f"[bold accent]{full_key}[/bold accent]",
            title="[warn]Your API Key (save it — shown only once)[/warn]",
            border_style="warn",
        ))
        _show_tool_config(full_key, provider)
    else:
        console.print(f"\n[muted]Selected existing key {key_prefix}… — full key is not stored.[/muted]")
        console.print("[muted]Run [bold]aigate onboard[/bold] again and create a new key if needed.[/muted]")

    console.print("\n[success bold]✓ Onboarding complete![/success bold]\n")
