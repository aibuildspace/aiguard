import asyncio

import typer
from aigate.cli.theme import console
from rich.table import Table

app = typer.Typer(help="View audit logs", no_args_is_help=True)


@app.command("list")
def list_logs(
    org: str = typer.Option(None, "--org", "-o", help="Filter by org slug"),
    outcome: str = typer.Option(None, "--outcome", help="clean | warned | blocked | sanitized"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """List recent audit log entries."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.audit_log import AuditLog
        from aigate.db.models.org import Org
        from sqlalchemy import select, desc

        async with async_session_factory() as session:
            q = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit)

            if org:
                result = await session.execute(select(Org).where(Org.slug == org))
                org_obj = result.scalar_one_or_none()
                if org_obj:
                    q = q.where(AuditLog.org_id == org_obj.id)

            if outcome:
                q = q.where(AuditLog.scan_outcome == outcome)

            result = await session.execute(q)
            logs = result.scalars().all()

        if not logs:
            console.print("[muted]No audit log entries found[/muted]")
            return

        table = Table("Timestamp", "Outcome", "Provider", "Model", "Shields", "Status")
        outcome_colors = {
            "clean": "success",
            "warned": "warn",
            "blocked": "error",
            "sanitized": "accent",
        }
        for log in logs:
            color = outcome_colors.get(log.scan_outcome, "white")
            shields = ", ".join(s.get("shield_id", s.get("skill_id", "")) for s in (log.skills_triggered or []))
            table.add_row(
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                f"[{color}]{log.scan_outcome}[/{color}]",
                log.provider,
                log.model[:30],
                shields[:40] or "—",
                str(log.http_status),
            )
        console.print(table)

    asyncio.run(_run())


@app.command("stats")
def stats(org: str = typer.Option(None, "--org", "-o")):
    """Show audit statistics."""
    async def _run():
        from aigate.db.engine import init_db
        await init_db()
        from aigate.db.engine import async_session_factory
        from aigate.db.models.audit_log import AuditLog
        from aigate.db.models.org import Org
        from sqlalchemy import select, func

        async with async_session_factory() as session:
            q = select(AuditLog.scan_outcome, func.count().label("count")).group_by(AuditLog.scan_outcome)

            if org:
                result = await session.execute(select(Org).where(Org.slug == org))
                org_obj = result.scalar_one_or_none()
                if org_obj:
                    q = q.where(AuditLog.org_id == org_obj.id)

            result = await session.execute(q)
            rows = result.all()

        table = Table("Outcome", "Count")
        for row in rows:
            table.add_row(row.scan_outcome, str(row.count))
        console.print(table)

    asyncio.run(_run())
