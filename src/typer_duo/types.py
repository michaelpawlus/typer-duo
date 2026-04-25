"""Public type aliases for typer-duo."""

from __future__ import annotations

from typing import Annotated

import typer

JsonFlag = Annotated[
    bool,
    typer.Option("--json", help="Output as JSON to stdout"),
]
"""Reusable annotated bool that exposes a ``--json`` flag on a Typer command.

Usage::

    from typer_duo import JsonFlag

    @app.command()
    def show(json_output: JsonFlag = False) -> None:
        ...
"""
