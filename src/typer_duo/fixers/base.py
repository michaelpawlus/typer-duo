"""Shared helpers for fixer modules."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from .models import FixEdit


def render_diff(edit: FixEdit) -> str:
    """Render a unified diff for *edit*. Empty if no real change."""
    if edit.is_noop:
        return ""
    a_label = "/dev/null" if edit.is_new else f"a/{edit.path}"
    b_label = f"b/{edit.path}"
    original = "" if edit.is_new else edit.original
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        edit.updated.splitlines(keepends=True),
        fromfile=a_label,
        tofile=b_label,
        n=3,
    )
    return "".join(diff)


def apply_edit(project_root: Path, edit: FixEdit) -> None:
    """Write *edit* to disk, creating parent dirs if necessary."""
    target = project_root / edit.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(edit.updated, encoding="utf-8")


def read_file(project_root: Path, relative: str) -> str:
    """Read *relative* under *project_root*. Returns "" if missing/unreadable."""
    path = project_root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def abs_pos(source: str, lineno: int, col_offset: int) -> int:
    """Convert a (1-indexed lineno, 0-indexed col) to an absolute char offset."""
    if lineno < 1:
        return 0
    pos = 0
    line = 1
    for i, ch in enumerate(source):
        if line == lineno:
            return i + col_offset
        if ch == "\n":
            line += 1
            pos = i + 1
    return pos + col_offset


def ensure_import(source: str, import_line: str) -> str:
    """Ensure *import_line* (e.g. ``"import sys"``) is present in *source*.

    Idempotent: if a matching ``import X`` (or ``from X import ...``) is
    already present, returns *source* unchanged. Otherwise inserts after the
    last top-level import block, or after the module docstring.
    """
    stripped = import_line.strip()
    if not stripped:
        return source

    # Match "import sys" or "from sys import ..." (handle simple cases).
    if stripped.startswith("import "):
        mod = stripped[len("import ") :].strip().split(" ")[0]
        # ``import sys`` is satisfied by ``import sys`` or ``from sys import ...``
        if re.search(rf"^\s*import\s+{re.escape(mod)}\b", source, re.MULTILINE):
            return source
        if re.search(rf"^\s*from\s+{re.escape(mod)}\s+import\s+", source, re.MULTILINE):
            return source
    else:
        if stripped in source:
            return source

    lines = source.splitlines(keepends=True)
    last_import = -1
    for i, line in enumerate(lines):
        s = line.lstrip()
        if s.startswith("import ") or s.startswith("from "):
            last_import = i

    new_line = import_line if import_line.endswith("\n") else import_line + "\n"

    if last_import == -1:
        # No imports yet: insert after a leading module docstring, if any.
        insert_at = _docstring_end_index(lines)
        lines.insert(insert_at, new_line)
        return "".join(lines)

    lines.insert(last_import + 1, new_line)
    return "".join(lines)


def _docstring_end_index(lines: list[str]) -> int:
    """Return the index after a leading triple-quoted module docstring."""
    if not lines:
        return 0
    first = lines[0].lstrip()
    if not (first.startswith('"""') or first.startswith("'''")):
        return 0
    quote = '"""' if first.startswith('"""') else "'''"
    # Single-line docstring like '"""hi"""\n'.
    if first.count(quote) >= 2:
        return 1
    for i in range(1, len(lines)):
        if quote in lines[i]:
            return i + 1
    return 0
