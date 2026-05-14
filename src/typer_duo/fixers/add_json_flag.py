"""Fixer: add ``json_output: JsonFlag = False`` to commands missing ``--json``.

This is the safe-by-default fixer for the audit's ``missing-json-flag``
finding. It reuses the AST utilities from :mod:`typer_duo.audit.diff` so the
``audit --fix-dry-run`` preview and the actual ``fix`` apply produce
identical edits.

Idempotent: a second run produces zero new edits because the AST walker only
selects commands whose signatures do not already expose a JSON parameter.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..audit.ast_walker import _find_commands
from ..audit.detectors import _arg_has_json_param
from ..audit.diff import _add_json_param_to_commands, _ensure_typer_duo_imports
from ..audit.models import AuditReport
from .base import read_file
from .models import FixEdit, FixResult

FIXER_ID = "add-json-flag"
ADDRESSES = ["missing-json-flag"]


def propose(project_root: Path, report: AuditReport) -> FixResult:
    """Build edits that add ``--json`` to every command lacking one."""
    if report.entry_point.framework == "unknown":
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason="no Typer entry point detected",
        )

    edits: list[FixEdit] = []
    # Group commands needing --json by source file.
    targets: dict[Path, list] = _collect_targets(project_root)

    for file_path, cmds in sorted(targets.items(), key=lambda kv: str(kv[0])):
        try:
            original = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        cmds_needing_json = [
            c for c in cmds if not c.is_on_duo_app and not _arg_has_json_param(c.func_node)
        ]
        if not cmds_needing_json:
            continue

        new_text = _add_json_param_to_commands(original, cmds_needing_json)
        new_text = _ensure_typer_duo_imports(new_text)

        if new_text == original:
            continue

        try:
            rel = str(file_path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(file_path)
        edits.append(FixEdit(path=rel, original=original, updated=new_text))

    if not edits:
        return FixResult(
            fixer_id=FIXER_ID,
            status="no-op",
            reason="every command already exposes --json",
            findings_addressed=ADDRESSES,
        )
    return FixResult(
        fixer_id=FIXER_ID,
        status="proposed",
        edits=edits,
        findings_addressed=ADDRESSES,
    )


def _collect_targets(project_root: Path) -> dict[Path, list]:
    """Walk the project once to collect Typer commands per source file."""
    from ..audit.ast_walker import _files_to_scan

    files = _files_to_scan(project_root, None, None)
    out: dict[Path, list] = {}
    for f in files:
        try:
            source = f.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue
        commands, _, _ = _find_commands(tree, f, project_root)
        if commands:
            out[f] = commands
    return out


# Silence "unused import" — kept so the audit code stays the single
# source of truth for what counts as a Typer command.
_ = read_file
