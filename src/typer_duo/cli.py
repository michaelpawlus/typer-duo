"""Top-level ``typer-duo`` CLI: ``init`` (scaffold) + ``audit``."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from .app import DuoApp
from .audit import audit_project
from .audit.models import severity_rank
from .constants import EXIT_ERROR, EXIT_NOT_FOUND, EXIT_OK
from .scaffold import init as _scaffold_init

app = DuoApp(
    name="typer-duo",
    help="Agent-ready dual-output toolkit for Typer CLIs.",
    no_args_is_help=True,
)


# Re-register the existing scaffold ``init`` command under the unified app.
# We pass ``duo=False`` because ``init`` already manages its own output style
# (writes to stderr via typer.echo) and returns nothing useful for JSON.
app.command(name="init", duo=False)(_scaffold_init)


@app.command(name="audit", duo=False)
def audit(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Directory of the Typer-based project to audit.",
        ),
    ],
    json_output: Annotated[
        bool, typer.Option("--json", help="Output structured JSON to stdout.")
    ] = False,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit non-zero if any finding has severity 'error'.",
        ),
    ] = False,
    fix_dry_run: Annotated[
        bool,
        typer.Option(
            "--fix-dry-run",
            help="Print the unified diff a hypothetical --fix would apply.",
        ),
    ] = False,
    include: Annotated[
        Optional[list[str]],
        typer.Option(
            "--include",
            help="Glob of .py files to include (relative to project root). Repeatable.",
        ),
    ] = None,
    exclude: Annotated[
        Optional[list[str]],
        typer.Option(
            "--exclude",
            help="Glob of .py files to exclude (relative to project root). Repeatable.",
        ),
    ] = None,
) -> None:
    """Audit an existing Typer CLI for agent-readiness.

    Performs a static AST analysis of the target project. Never executes the
    target. Reports which commands lack ``--json``, which use bare ``print()``,
    and (with ``--fix-dry-run``) emits a migration diff.
    """
    report = audit_project(
        project_root=path,
        include=include,
        exclude=exclude,
        fix_dry_run=fix_dry_run,
    )

    if report.entry_point.framework == "unknown":
        payload = {"error": "no Typer entry point detected", "code": EXIT_NOT_FOUND}
        if json_output:
            _json.dump(payload, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"Error: {payload['error']} (path: {path})", file=sys.stderr)
        raise typer.Exit(EXIT_NOT_FOUND)

    if json_output:
        _json.dump(report.to_dict(), sys.stdout, default=str)
        sys.stdout.write("\n")
    else:
        _render_human(report)

    if strict and report.severity_max == "error":
        raise typer.Exit(EXIT_ERROR)
    raise typer.Exit(EXIT_OK)


def _render_human(report) -> None:  # noqa: ANN001 (report is AuditReport)
    """Write a concise human-readable summary to stderr."""
    ep = report.entry_point
    print(f"Audited: {report.path}", file=sys.stderr)
    print(
        f"  entry: {ep.script_name or '?'}  "
        f"({ep.module}:{ep.app_var}, framework={ep.framework})",
        file=sys.stderr,
    )
    print(
        f"  commands: {report.commands_total}  "
        f"with --json: {report.commands_with_json}  "
        f"using print(): {report.commands_using_print}  "
        f"score: {report.score}%",
        file=sys.stderr,
    )

    if not report.findings:
        print("  no findings", file=sys.stderr)
    else:
        print("  findings:", file=sys.stderr)
        ordered = sorted(
            report.findings,
            key=lambda f: (-severity_rank(f.severity), f.file, f.line),
        )
        for f in ordered:
            location = f"{f.file}:{f.line}"
            cmd_part = f" [{f.command}]" if f.command else ""
            print(
                f"    {f.severity:<7} {f.id:<22} {location}{cmd_part}  {f.detail}",
                file=sys.stderr,
            )

    if report.diff_preview:
        print("--- diff preview ---", file=sys.stderr)
        print(report.diff_preview, file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    app()
