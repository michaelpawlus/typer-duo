"""Mixed fixture: half migrated, half not."""

from typing import Annotated

import typer
from rich.console import Console

console = Console()  # missing stderr=True
app = typer.Typer(name="mixed")


@app.command()
def good(
    name: str,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> dict:
    """Already exposes --json."""
    return {"name": name}


@app.command()
def bad(name: str) -> None:
    """Plain print, no --json."""
    print(f"hello {name}")
    console.print("done")
