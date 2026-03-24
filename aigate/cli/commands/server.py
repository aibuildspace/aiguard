import typer
from aigate.cli.theme import console
from rich.table import Table

app = typer.Typer(help="Server management", no_args_is_help=True)


@app.command("status")
def status():
    """Check if the AIGate server is running."""
    import httpx
    from aigate.config import settings

    url = f"http://{settings.host}:{settings.port}/health"
    try:
        resp = httpx.get(url, timeout=3.0)
        data = resp.json()
        console.print(f"[success]✓ AIGate is running[/success] — {data.get('shields_loaded', 0)} shields loaded")
    except Exception:
        console.print("[error]✗ AIGate is not running[/error]")
        raise typer.Exit(1)
