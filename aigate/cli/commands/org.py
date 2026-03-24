import asyncio
import json

import typer
from aigate.cli.theme import console
from rich.table import Table

app = typer.Typer(help="Manage organisations", no_args_is_help=True)


@app.command("create")
def create_org(
    name: str = typer.Option(..., "--name", "-n", help="Organisation name"),
    slug: str = typer.Option(None, "--slug", help="URL-safe slug (auto-derived if omitted)"),
):
    """Create a new organisation."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org
        import re

        from sqlalchemy.exc import IntegrityError

        _slug = slug or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32]
        org = Org(name=name, slug=_slug)
        try:
            async with async_session_factory() as session:
                session.add(org)
                await session.commit()
                await session.refresh(org)
        except IntegrityError:
            console.print(f"[warn]Org with slug '{_slug}' already exists[/warn]")
            return
        console.print(f"[success]✓ Created org[/success] [bold]{org.name}[/bold] (slug: {org.slug}, id: {org.id})")

    asyncio.run(_run())


@app.command("list")
def list_orgs():
    """List all organisations."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(Org))
            orgs = result.scalars().all()

        table = Table("ID", "Name", "Slug", "Users", "Keys")
        for org in orgs:
            table.add_row(
                str(org.id)[:8] + "...",
                org.name,
                org.slug,
                str(len(org.users)),
                str(len(org.api_keys)),
            )
        console.print(table)

    asyncio.run(_run())


@app.command("policy")
def set_policy(
    slug: str = typer.Argument(..., help="Org slug"),
    policy_json: str = typer.Option(None, "--set", help="JSON policy string"),
):
    """View or set org policy."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.org import Org
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(Org).where(Org.slug == slug))
            org = result.scalar_one_or_none()
            if not org:
                console.print(f"[error]Org '{slug}' not found[/error]")
                raise typer.Exit(1)

            if policy_json:
                try:
                    org.policy = json.loads(policy_json)
                    await session.commit()
                    console.print(f"[success]✓ Policy updated for {slug}[/success]")
                except json.JSONDecodeError as e:
                    console.print(f"[error]Invalid JSON: {e}[/error]")
                    raise typer.Exit(1)
            else:
                console.print_json(json.dumps(org.policy, indent=2))

    asyncio.run(_run())
