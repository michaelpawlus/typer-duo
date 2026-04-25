"""Generate a unified migration diff for ``--fix-dry-run``.

The diff is preview-only: ``audit`` never writes back to disk in v0.1.0.
It rewrites the entry-point module to use ``DuoApp`` and adds a
``json_output: JsonFlag = False`` parameter to commands that lack one.

It does NOT rewrite ``print()`` calls.
"""

from __future__ import annotations

import ast
import difflib
import re
from pathlib import Path

from .detectors import CommandInfo, _arg_has_json_param
from .models import EntryPoint


def build_dry_run_diff(
    project_root: Path,
    entry: EntryPoint,
    commands: list[CommandInfo],
) -> str | None:
    """Return a unified diff representing the conservative migration.

    Returns ``None`` if no migration changes are needed.
    """
    if entry.file is None:
        return None

    # Group commands by file so each file is rewritten once.
    by_file: dict[Path, list[CommandInfo]] = {}
    for cmd in commands:
        by_file.setdefault(Path(cmd.file), []).append(cmd)

    entry_path = Path(entry.file)
    if entry_path not in by_file:
        by_file[entry_path] = []

    diff_parts: list[str] = []
    for file_path, cmds in sorted(by_file.items(), key=lambda kv: str(kv[0])):
        try:
            original = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        new_text = original
        is_entry = file_path.resolve() == entry_path.resolve()
        if is_entry and entry.framework == "typer":
            new_text = _migrate_entry_point(new_text, entry.app_var or "app")

        # Add json_output param to commands that lack one (and are not on a DuoApp).
        cmds_needing_json = [
            c
            for c in cmds
            if not c.is_on_duo_app and not _arg_has_json_param(c.func_node)
        ]
        if cmds_needing_json:
            new_text = _add_json_param_to_commands(new_text, cmds_needing_json)
            new_text = _ensure_typer_duo_imports(new_text)

        if new_text == original:
            continue
        rel = str(file_path.resolve().relative_to(project_root.resolve()))
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=rel,
            tofile=rel,
        )
        diff_parts.append("".join(diff))

    if not diff_parts:
        return None
    return "\n".join(diff_parts)


def _migrate_entry_point(source: str, app_var: str) -> str:
    """Replace ``import typer`` + ``app = typer.Typer(...)`` with DuoApp.

    Conservative: leaves the rest of the imports alone.
    """
    out = source

    # 1. Replace ``app = typer.Typer(`` with ``app = DuoApp(`` for *app_var*.
    pattern = re.compile(
        rf"(^|\n)(\s*){re.escape(app_var)}\s*=\s*typer\.Typer\(",
        flags=re.MULTILINE,
    )
    out = pattern.sub(rf"\1\2{app_var} = DuoApp(", out)

    return out


def _ensure_typer_duo_imports(source: str) -> str:
    """Ensure ``from typer_duo import DuoApp, JsonFlag`` (and duo_print) is present.

    Adds a single import line at the first reasonable spot if not present.
    """
    needed = []
    if "from typer_duo" not in source:
        needed = ["DuoApp", "JsonFlag"]
        new_import = "from typer_duo import DuoApp, JsonFlag\n"
        return _insert_import(source, new_import)

    # If the existing typer_duo import is missing JsonFlag, expand it.
    m = re.search(r"^from\s+typer_duo\s+import\s+([^\n]+)$", source, flags=re.MULTILINE)
    if m:
        existing = [s.strip() for s in m.group(1).split(",")]
        if "JsonFlag" not in existing:
            existing.append("JsonFlag")
            replacement = f"from typer_duo import {', '.join(sorted(set(existing)))}"
            source = source[: m.start()] + replacement + source[m.end():]
        if "DuoApp" not in existing and "DuoApp" in source:
            # if DuoApp is referenced but not imported, add it.
            existing.append("DuoApp")
            replacement = f"from typer_duo import {', '.join(sorted(set(existing)))}"
            source = re.sub(
                r"^from\s+typer_duo\s+import\s+[^\n]+$",
                replacement,
                source,
                count=1,
                flags=re.MULTILINE,
            )

    return source


def _insert_import(source: str, import_line: str) -> str:
    """Insert *import_line* after the last top-level import block."""
    lines = source.splitlines(keepends=True)
    last_import = -1
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import = i
    if last_import == -1:
        # Insert after a leading docstring or at the top.
        return import_line + source
    insert_at = last_import + 1
    lines.insert(insert_at, import_line)
    return "".join(lines)


def _add_json_param_to_commands(source: str, cmds: list[CommandInfo]) -> str:
    """Append ``json_output: JsonFlag = False`` to each command's signature.

    Operates on the source text using AST line/column info so we touch one
    function at a time without disturbing the rest of the file.
    """
    # Sort by lineno descending so insertions don't shift earlier offsets.
    cmds_sorted = sorted(cmds, key=lambda c: c.func_node.lineno, reverse=True)
    for cmd in cmds_sorted:
        source = _add_json_param_to_function(source, cmd.func_node)
    return source


def _add_json_param_to_function(
    source: str, func: ast.FunctionDef | ast.AsyncFunctionDef
) -> str:
    """Insert ``json_output: JsonFlag = False`` before the closing ``)`` of *func*."""
    # Locate the opening ``def name(`` line via lineno/col_offset.
    lines = source.splitlines(keepends=True)
    idx = func.lineno - 1
    if idx < 0 or idx >= len(lines):
        return source

    # Find the closing ``)`` of the def signature, possibly across multiple lines.
    # We scan from the opening paren on or after func.col_offset.
    abs_pos = sum(len(line) for line in lines[:idx]) + func.col_offset
    open_paren = source.find("(", abs_pos)
    if open_paren == -1:
        return source
    close_paren = _find_matching_paren(source, open_paren)
    if close_paren == -1:
        return source

    # Build the new param.
    sig_text = source[open_paren + 1 : close_paren]
    has_args = sig_text.strip() != ""
    new_param = "json_output: JsonFlag = False"
    if has_args:
        # Try to preserve indentation if the signature is multi-line.
        if "\n" in sig_text:
            # Match the indent of the last param line.
            tail_indent_match = re.search(r"\n([ \t]*)[^\n]*$", sig_text)
            indent = tail_indent_match.group(1) if tail_indent_match else "    "
            insertion = f",\n{indent}{new_param}"
        else:
            insertion = f", {new_param}"
    else:
        insertion = new_param

    return source[: close_paren] + insertion + source[close_paren:]


def _find_matching_paren(source: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    in_string: str | None = None
    while i < len(source):
        ch = source[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1
