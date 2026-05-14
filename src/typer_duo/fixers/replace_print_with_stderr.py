"""Fixer: route bare ``print(...)`` calls inside commands to ``sys.stderr``.

Targets the audit's ``bare-print-stdout`` warning. The fix is conservative:
we only rewrite ``print(...)`` calls whose AST sits inside a discovered
Typer command body, and we leave existing keyword arguments alone — we
only add ``file=sys.stderr`` when no ``file=`` keyword is already present.

Idempotent: an already-redirected ``print(..., file=sys.stderr)`` is not
matched a second time.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..audit.ast_walker import _find_commands, _files_to_scan
from ..audit.models import AuditReport
from .base import abs_pos, ensure_import
from .models import FixEdit, FixResult

FIXER_ID = "replace-print-with-stderr"
ADDRESSES = ["bare-print-stdout"]


def propose(project_root: Path, report: AuditReport) -> FixResult:
    if report.entry_point.framework == "unknown":
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason="no Typer entry point detected",
        )

    files = _files_to_scan(project_root, None, None)
    edits: list[FixEdit] = []

    for file_path in files:
        try:
            original = file_path.read_text(encoding="utf-8")
            tree = ast.parse(original)
        except (SyntaxError, OSError):
            continue

        commands, _, _ = _find_commands(tree, file_path, project_root)
        if not commands:
            continue

        targets = _collect_print_calls(commands)
        if not targets:
            continue

        new_text = _rewrite_prints(original, targets)
        if new_text == original:
            continue
        new_text = ensure_import(new_text, "import sys")

        try:
            rel = str(file_path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(file_path)
        edits.append(FixEdit(path=rel, original=original, updated=new_text))

    if not edits:
        return FixResult(
            fixer_id=FIXER_ID,
            status="no-op",
            reason="no bare print() calls in commands",
            findings_addressed=ADDRESSES,
        )
    return FixResult(
        fixer_id=FIXER_ID,
        status="proposed",
        edits=edits,
        findings_addressed=ADDRESSES,
    )


def _collect_print_calls(commands) -> list[ast.Call]:
    """Find ``print(...)`` calls (no existing ``file=stderr``) inside commands."""
    out: list[ast.Call] = []
    for cmd in commands:
        for node in ast.walk(cmd.func_node):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                continue
            if _already_stderr(node):
                continue
            out.append(node)
    return out


def _already_stderr(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "file":
            target = kw.value
            if isinstance(target, ast.Attribute) and target.attr == "stderr":
                return True
            if isinstance(target, ast.Name) and target.id == "stderr":
                return True
    return False


def _rewrite_prints(source: str, calls: list[ast.Call]) -> str:
    """Insert ``file=sys.stderr`` into each call. Process tail-first to keep offsets valid."""
    # Sort by end position descending so earlier offsets stay valid.
    ordered = sorted(
        calls,
        key=lambda c: (c.end_lineno or 0, c.end_col_offset or 0),
        reverse=True,
    )
    out = source
    for call in ordered:
        out = _insert_file_kwarg(out, call)
    return out


def _insert_file_kwarg(source: str, call: ast.Call) -> str:
    if call.end_lineno is None or call.end_col_offset is None:
        return source
    end_abs = abs_pos(source, call.end_lineno, call.end_col_offset)
    # end_col_offset points one past the closing `)`.
    close_pos = end_abs - 1
    if close_pos < 0 or close_pos >= len(source) or source[close_pos] != ")":
        return source

    n_args = len(call.args) + len(call.keywords)

    if n_args == 0:
        return source[:close_pos] + "file=sys.stderr" + source[close_pos:]

    # Scan back for the last meaningful char before `)` to decide whether a
    # trailing comma is already there.
    i = close_pos - 1
    while i > 0 and source[i] in " \t\n":
        i -= 1
    if i >= 0 and source[i] == ",":
        return source[:close_pos] + "file=sys.stderr" + source[close_pos:]
    return source[:close_pos] + ", file=sys.stderr" + source[close_pos:]
