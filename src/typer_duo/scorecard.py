"""Aggregated portfolio-wide audit scorecard.

Used by ``typer-duo audit-all`` to roll up per-project ``AuditReport`` records
into a single JSON artifact suitable for diffing over time and for
consumption by ``conductor doctor`` and ``code-daily portfolio sweep``.

Schema is documented inline on :class:`Scorecard` and stays stable through
the ``schema_version`` field so consumers can guard against future changes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

from .audit.models import AuditReport

SCHEMA_VERSION = 1

ProjectStatus = Literal["ok", "warn", "fail", "no-cli", "non-typer"]
CheckStatus = Literal["pass", "warn", "fail"]


CHECK_NAMES: tuple[str, ...] = (
    "json_flag_parity",
    "error_shape",
    "duo_registered",
    "exit_codes",
)


@dataclass
class ProjectScore:
    """Scorecard entry for one project.

    ``score`` is the AST audit's per-project score normalized to [0.0, 1.0],
    or ``None`` when the project has no Typer CLI to audit. ``checks`` is a
    rollup of audit findings into the four buckets the spec calls out.
    ``commands_failing`` lists command names that triggered an error-level
    finding so users can see exactly what to fix.
    """

    name: str
    path: str
    status: ProjectStatus
    score: float | None
    checks: dict[str, CheckStatus] = field(default_factory=dict)
    commands_audited: int = 0
    commands_failing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "status": self.status,
            "score": self.score,
        }
        if self.status not in ("no-cli",):
            out["checks"] = dict(self.checks)
            out["commands_audited"] = self.commands_audited
            out["commands_failing"] = list(self.commands_failing)
        return out


@dataclass
class PortfolioSummary:
    total_projects: int = 0
    with_cli: int = 0
    passing: int = 0
    warning: int = 0
    failing: int = 0
    no_cli: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_projects": self.total_projects,
            "with_cli": self.with_cli,
            "passing": self.passing,
            "warning": self.warning,
            "failing": self.failing,
            "no_cli": self.no_cli,
        }


@dataclass
class Scorecard:
    """Top-level portfolio scorecard.

    ``portfolio_score`` is the simple mean of per-project scores, ignoring
    projects with ``score=None`` (no CLI / non-Typer). It is ``None`` when
    no scorable projects were found.
    """

    generated_at: str
    root: str
    projects: list[ProjectScore] = field(default_factory=list)
    portfolio_score: float | None = None
    summary: PortfolioSummary = field(default_factory=PortfolioSummary)
    diff: dict[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "root": self.root,
            "portfolio_score": self.portfolio_score,
            "projects": [p.to_dict() for p in self.projects],
            "summary": self.summary.to_dict(),
        }
        if self.diff is not None:
            out["diff"] = self.diff
        return out


def _checks_from_report(report: AuditReport) -> tuple[dict[str, CheckStatus], list[str]]:
    """Roll the flat finding list up into the four spec buckets.

    Mapping:

    - ``json_flag_parity``  ← ``missing-json-flag`` (error → fail)
    - ``duo_registered``    ← ``app-uses-plain-typer`` (warning → warn)
    - ``error_shape``       ← ``bare-print-stdout`` (warning → warn);
      bare prints to stdout corrupt JSON output, which is the closest the
      static audit gets to checking error/output shape.
    - ``exit_codes``        ← always ``pass``; the static audit cannot
      observe runtime exit codes, so we report ``pass`` rather than fake a
      signal we do not have.
    """
    checks: dict[str, CheckStatus] = {name: "pass" for name in CHECK_NAMES}
    failing_commands: list[str] = []
    for f in report.findings:
        if f.id == "missing-json-flag":
            checks["json_flag_parity"] = "fail"
            if f.command:
                failing_commands.append(f.command)
        elif f.id == "app-uses-plain-typer":
            if checks["duo_registered"] != "fail":
                checks["duo_registered"] = "warn"
        elif f.id == "bare-print-stdout":
            if checks["error_shape"] != "fail":
                checks["error_shape"] = "warn"
    # De-dupe while preserving discovery order.
    seen: set[str] = set()
    deduped: list[str] = []
    for c in failing_commands:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return checks, deduped


def score_from_report(name: str, path: str, report: AuditReport) -> ProjectScore:
    """Map an :class:`AuditReport` to a :class:`ProjectScore`.

    A report whose entry point is ``unknown`` (no Typer app detected) is
    reported as ``status='non-typer'`` with ``score=None`` — distinct from
    ``no-cli`` so callers can see the difference between "no CLI declared"
    and "CLI declared but not Typer-based".
    """
    if report.entry_point.framework == "unknown":
        return ProjectScore(
            name=name, path=path, status="non-typer", score=None,
        )

    checks, failing = _checks_from_report(report)
    sev = report.severity_max
    if sev == "error":
        status: ProjectStatus = "fail"
    elif sev == "warning":
        status = "warn"
    else:
        status = "ok"
    score = round(report.score / 100, 2)
    return ProjectScore(
        name=name,
        path=path,
        status=status,
        score=score,
        checks=checks,
        commands_audited=report.commands_total,
        commands_failing=failing,
    )


def no_cli_score(name: str, path: str) -> ProjectScore:
    """Build a no-CLI placeholder entry."""
    return ProjectScore(name=name, path=path, status="no-cli", score=None)


def build_scorecard(
    root: str,
    projects: list[ProjectScore],
    *,
    generated_at: str | None = None,
    diff: dict[str, Any] | None = None,
) -> Scorecard:
    """Assemble a :class:`Scorecard` from per-project entries."""
    if generated_at is None:
        generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    summary = PortfolioSummary(total_projects=len(projects))
    scorables: list[float] = []
    for p in projects:
        if p.status == "no-cli":
            summary.no_cli += 1
            continue
        if p.status == "non-typer":
            # Counted as with_cli (it does have scripts) but not scorable.
            summary.with_cli += 1
            continue
        summary.with_cli += 1
        if p.status == "ok":
            summary.passing += 1
        elif p.status == "warn":
            summary.warning += 1
        elif p.status == "fail":
            summary.failing += 1
        if p.score is not None:
            scorables.append(p.score)

    portfolio = round(sum(scorables) / len(scorables), 2) if scorables else None
    return Scorecard(
        generated_at=generated_at,
        root=root,
        projects=projects,
        portfolio_score=portfolio,
        summary=summary,
        diff=diff,
    )


def compute_diff(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Diff two scorecards (as ``to_dict()`` payloads).

    Keys:
      - ``vs_baseline``: baseline's ``generated_at`` for traceability
      - ``improved``: project names whose score went up
      - ``regressed``: project names whose score went down
      - ``newly_added``: project names present in *current* but not in baseline
      - ``removed``: project names present in baseline but not in *current*
    """
    cur_by_name = {p["name"]: p for p in current.get("projects", [])}
    base_by_name = {p["name"]: p for p in baseline.get("projects", [])}

    improved: list[str] = []
    regressed: list[str] = []
    for name, cur in cur_by_name.items():
        base = base_by_name.get(name)
        if base is None:
            continue
        cs, bs = cur.get("score"), base.get("score")
        if cs is None or bs is None:
            continue
        if cs > bs:
            improved.append(name)
        elif cs < bs:
            regressed.append(name)

    newly_added = sorted(set(cur_by_name) - set(base_by_name))
    removed = sorted(set(base_by_name) - set(cur_by_name))

    return {
        "vs_baseline": baseline.get("generated_at"),
        "improved": sorted(improved),
        "regressed": sorted(regressed),
        "newly_added": newly_added,
        "removed": removed,
    }
