"""Fixer: add a ``[project.scripts]`` entry pointing at the discovered Typer app.

Runs when audit detected a Typer/DuoApp module but the ``pyproject.toml``
has no script entry mapping to it. We do not overwrite existing entries.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ..audit.models import AuditReport
from .models import FixEdit, FixResult

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

FIXER_ID = "add-project-script-entry"
ADDRESSES: list[str] = []  # Not tied to a specific finding ID; runs from entry-point state.


def propose(project_root: Path, report: AuditReport) -> FixResult:
    ep = report.entry_point
    if ep.framework == "unknown" or ep.module is None or ep.app_var is None:
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason="no Typer entry point detected",
        )

    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason="no pyproject.toml at project root",
        )

    try:
        original = pyproject.read_text(encoding="utf-8")
    except OSError as exc:
        return FixResult(
            fixer_id=FIXER_ID,
            status="error",
            reason=f"could not read pyproject.toml: {exc}",
        )

    try:
        data = tomllib.loads(original)
    except tomllib.TOMLDecodeError as exc:
        return FixResult(
            fixer_id=FIXER_ID,
            status="error",
            reason=f"pyproject.toml is not valid TOML: {exc}",
        )

    target = f"{ep.module}:{ep.app_var}"
    existing_scripts = data.get("project", {}).get("scripts", {}) or {}
    if any(v == target for v in existing_scripts.values()):
        return FixResult(
            fixer_id=FIXER_ID,
            status="no-op",
            reason=f"[project.scripts] already maps to {target}",
        )

    project_name = data.get("project", {}).get("name") or project_root.name
    script_name = _default_script_name(project_name)

    # Make sure we don't collide with an existing script of the same name.
    if script_name in existing_scripts:
        return FixResult(
            fixer_id=FIXER_ID,
            status="skipped",
            reason=(
                f"[project.scripts] already defines '{script_name}' "
                f"(pointing elsewhere); refusing to overwrite"
            ),
        )

    updated = _insert_script_entry(original, script_name, target)
    if updated == original:
        return FixResult(
            fixer_id=FIXER_ID,
            status="error",
            reason="could not figure out where to insert [project.scripts]",
        )

    edit = FixEdit(path="pyproject.toml", original=original, updated=updated)
    return FixResult(
        fixer_id=FIXER_ID,
        status="proposed",
        edits=[edit],
        findings_addressed=ADDRESSES,
    )


def _default_script_name(project_name: str) -> str:
    """Pick a console script name from the project name (PEP 503-ish slug)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", project_name).strip("-").lower()
    return slug or "app"


def _insert_script_entry(source: str, name: str, target: str) -> str:
    """Insert (or extend) ``[project.scripts]`` with ``name = "target"``.

    Handles three cases:
    1. ``[project.scripts]`` table exists -- append the line at end of section.
    2. ``[project]`` table exists, no scripts subtable -- insert a new
       ``[project.scripts]`` section right after the [project] block.
    3. No ``[project]`` table -- append the section at the end of the file.
    """
    new_line = f'{name} = "{target}"'
    scripts_header = re.compile(r"^\[project\.scripts\]\s*$", re.MULTILINE)
    project_header = re.compile(r"^\[project\]\s*$", re.MULTILINE)

    m = scripts_header.search(source)
    if m:
        end_of_section = _section_end(source, m.end())
        body = source[m.end():end_of_section]
        # Avoid double-insert if for some reason it's already there.
        if re.search(rf"^\s*{re.escape(name)}\s*=", body, re.MULTILINE):
            return source
        # Ensure trailing newline before insert.
        prefix = source[:end_of_section]
        if not prefix.endswith("\n"):
            prefix = prefix + "\n"
        return prefix + new_line + "\n" + source[end_of_section:]

    m = project_header.search(source)
    if m:
        end_of_section = _section_end(source, m.end())
        prefix = source[:end_of_section]
        if not prefix.endswith("\n"):
            prefix = prefix + "\n"
        block = f"\n[project.scripts]\n{new_line}\n"
        return prefix + block + source[end_of_section:]

    # No [project] section -- append at end.
    suffix = source if source.endswith("\n") else source + "\n"
    block = f"\n[project.scripts]\n{new_line}\n"
    return suffix + block


def _section_end(source: str, start: int) -> int:
    """Return the index at which the TOML section starting at *start* ends.

    A section ends at the next ``^[...]`` header or end-of-file.
    """
    next_header = re.search(r"^\[", source[start:], re.MULTILINE)
    if not next_header:
        return len(source)
    return start + next_header.start()
