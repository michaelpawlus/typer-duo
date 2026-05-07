"""Top-level ``typer-duo`` CLI: ``init`` (scaffold) + ``audit`` + ``audit-all``."""

from __future__ import annotations

import concurrent.futures
import json as _json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from .app import DuoApp
from .audit import audit_project
from .audit.models import severity_rank
from .constants import EXIT_ERROR, EXIT_NOT_FOUND, EXIT_OK
from .discovery import ProjectPath, iter_projects
from .scaffold import init as _scaffold_init
from .scorecard import (
    Scorecard,
    build_scorecard,
    compute_diff,
    no_cli_score,
    score_from_report,
)

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


@app.command(name="audit-all", duo=False)
def audit_all(
    root: Annotated[
        Path,
        typer.Option(
            "--root",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
            help="Root directory to walk (default: ~/projects).",
        ),
    ] = Path("~/projects").expanduser(),
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON scorecard to stdout."),
    ] = False,
    include: Annotated[
        Optional[list[str]],
        typer.Option(
            "--include",
            help="Glob of project dir names to include (repeatable).",
        ),
    ] = None,
    exclude: Annotated[
        Optional[list[str]],
        typer.Option(
            "--exclude",
            help="Glob of project dir names to exclude (repeatable).",
        ),
    ] = None,
    since: Annotated[
        Optional[Path],
        typer.Option(
            "--since",
            exists=True,
            file_okay=True,
            dir_okay=False,
            help="Compare against a previous scorecard JSON file.",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            help="Write scorecard JSON to this file (also stdout if --json).",
        ),
    ] = None,
    fail_under: Annotated[
        Optional[float],
        typer.Option(
            "--fail-under",
            help="Exit non-zero if portfolio_score is below this threshold (0..1).",
        ),
    ] = None,
    skip_no_cli: Annotated[
        bool,
        typer.Option(
            "--skip-no-cli",
            help="Skip projects with no CLI entry point in the scorecard.",
        ),
    ] = False,
    workers: Annotated[
        int,
        typer.Option(
            "--workers",
            min=1,
            max=32,
            help="Parallel worker count for per-project audits.",
        ),
    ] = 4,
) -> None:
    """Run the per-project audit across every project under ``--root``.

    Produces an aggregated scorecard suitable for diffing over time and for
    feeding into ``conductor doctor`` and ``code-daily portfolio sweep``.
    """
    discovered = list(iter_projects(root, include=include, exclude=exclude))

    project_scores = _audit_in_parallel(
        discovered, skip_no_cli=skip_no_cli, max_workers=workers
    )

    diff = None
    if since is not None:
        try:
            baseline = _json.loads(since.read_text(encoding="utf-8"))
        except (OSError, _json.JSONDecodeError) as exc:
            payload = {"error": f"could not read --since file: {exc}", "code": EXIT_ERROR}
            if json_output:
                _json.dump(payload, sys.stdout)
                sys.stdout.write("\n")
            else:
                print(f"Error: {payload['error']}", file=sys.stderr)
            raise typer.Exit(EXIT_ERROR)

    scorecard = build_scorecard(root=str(root), projects=project_scores)
    if since is not None:
        scorecard.diff = compute_diff(scorecard.to_dict(), baseline)

    payload = scorecard.to_dict()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if json_output:
        _json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
    else:
        _render_audit_all_human(scorecard)

    if fail_under is not None:
        if scorecard.portfolio_score is None or scorecard.portfolio_score < fail_under:
            raise typer.Exit(EXIT_ERROR)
    raise typer.Exit(EXIT_OK)


def _audit_one(project: ProjectPath, *, skip_no_cli: bool):
    """Audit a single discovered project. Returns a ProjectScore or None."""
    if not project.has_scripts:
        if skip_no_cli:
            return None
        return no_cli_score(project.name, str(project.path))
    report = audit_project(project_root=project.path)
    return score_from_report(project.name, str(project.path), report)


def _audit_in_parallel(
    projects: list[ProjectPath], *, skip_no_cli: bool, max_workers: int
) -> list:
    """Run per-project audits concurrently, preserving discovery order."""
    if not projects:
        return []
    results: list = [None] * len(projects)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_audit_one, p, skip_no_cli=skip_no_cli): i
            for i, p in enumerate(projects)
        }
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
    return [r for r in results if r is not None]


def _render_audit_all_human(scorecard: Scorecard) -> None:
    """Write a concise human summary of the scorecard to stderr."""
    s = scorecard.summary
    print(f"Portfolio root: {scorecard.root}", file=sys.stderr)
    print(
        f"  projects: {s.total_projects}  "
        f"with-cli: {s.with_cli}  no-cli: {s.no_cli}",
        file=sys.stderr,
    )
    score = scorecard.portfolio_score
    score_str = f"{score:.2f}" if score is not None else "n/a"
    print(
        f"  passing: {s.passing}  warning: {s.warning}  "
        f"failing: {s.failing}  portfolio_score: {score_str}",
        file=sys.stderr,
    )

    # Group failing/warning projects first so attention goes there.
    order = {"fail": 0, "warn": 1, "non-typer": 2, "ok": 3, "no-cli": 4}
    sorted_projects = sorted(
        scorecard.projects, key=lambda p: (order.get(p.status, 9), p.name)
    )
    for p in sorted_projects:
        score_repr = f"{p.score:.2f}" if p.score is not None else "  --"
        line = f"  [{p.status:<9}] {score_repr}  {p.name}"
        print(line, file=sys.stderr)
        if p.commands_failing:
            print(
                f"      failing: {', '.join(p.commands_failing)}",
                file=sys.stderr,
            )

    if scorecard.diff is not None:
        d = scorecard.diff
        print(f"  diff vs {d.get('vs_baseline')}:", file=sys.stderr)
        for key in ("improved", "regressed", "newly_added", "removed"):
            vals = d.get(key) or []
            if vals:
                print(f"    {key}: {', '.join(vals)}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    app()
