"""DuoApp fixture: fully agent-compat."""

import sys

from rich.console import Console

from typer_duo import DuoApp, duo_print

err = Console(stderr=True)
app = DuoApp(name="duo-typer")


@app.command()
def setup(name: str) -> dict:
    """Set up the thing."""
    duo_print(f"Created config at /tmp/{name}")
    return {"name": name, "status": "ok"}


@app.command()
def status() -> dict:
    """Show status."""
    print("about to check", file=sys.stderr)
    return {"status": "ok"}
