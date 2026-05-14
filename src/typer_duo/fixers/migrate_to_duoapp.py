"""Fixer: rewrite ``app = typer.Typer(...)`` to ``app = DuoApp(...)``.

Opt-in only. Never runs unless the user explicitly passes ``--check
migrate-to-duoapp`` because it changes the runtime behaviour of every
command in the entry-point module (each one suddenly gains a ``--json``
flag managed by ``DuoApp``).

Reuses :func:`typer_duo.audit.diff._migrate_entry_point` and
:func:`_ensure_typer_duo_imports` so the edit matches the audit
``--fix-dry-run`` preview exactly.
"""

from __future__ import annotations

from pathlib import Path

from ..audit.diff import _ensure_typer_duo_imports, _migrate_entry_point
from ..audit.models import AuditReport
from .models import FixEdit, FixResult

FIXER_ID = "migrate-to-duoapp"
ADDRESSES = ["app-uses-plain-typer"]


def propose(project_root: Path, report: AuditReport) -> FixResult:
    ep = report.entry_point
    if ep.framework == "unknown":
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason="no Typer entry point detected",
        )
    if ep.framework == "duo":
        return FixResult(
            fixer_id=FIXER_ID,
            status="no-op",
            reason="entry point already uses DuoApp",
            findings_addressed=ADDRESSES,
        )
    if ep.file is None or ep.app_var is None:
        return FixResult(
            fixer_id=FIXER_ID,
            status="error",
            reason="entry point detected but missing file/app_var info",
        )

    file_path = Path(ep.file)
    try:
        original = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return FixResult(
            fixer_id=FIXER_ID,
            status="error",
            reason=f"could not read entry-point file: {exc}",
        )

    migrated = _migrate_entry_point(original, ep.app_var)
    if migrated == original:
        return FixResult(
            fixer_id=FIXER_ID,
            status="no-op",
            reason="no `typer.Typer(` assignment matched the entry-point var",
        )
    migrated = _ensure_typer_duo_imports(migrated)

    try:
        rel = str(file_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel = str(file_path)

    edit = FixEdit(path=rel, original=original, updated=migrated)
    return FixResult(
        fixer_id=FIXER_ID,
        status="proposed",
        edits=[edit],
        findings_addressed=ADDRESSES,
    )
