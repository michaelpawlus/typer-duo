"""Plain Typer fixture: needs migration."""

import typer

app = typer.Typer(name="plain-typer")


@app.command()
def setup(name: str) -> None:
    """Set up the thing."""
    print(f"Created config at /tmp/{name}")


@app.command()
def status() -> None:
    """Show status."""
    print("OK")
