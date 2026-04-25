"""Tests for the --fix-dry-run diff generator."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

from typer_duo.audit import audit_project

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def test_diff_preview_present_for_plain_typer():
    report = audit_project(FIXTURES / "plain-typer", fix_dry_run=True)
    assert report.diff_preview is not None
    assert "DuoApp" in report.diff_preview
    assert "json_output: JsonFlag = False" in report.diff_preview


def test_diff_preview_absent_when_no_changes():
    report = audit_project(FIXTURES / "duo-typer", fix_dry_run=True)
    assert report.diff_preview is None


def _apply_unified_diff(diff: str, root: Path) -> None:
    """Minimal unified-diff applier for our own preview format.

    Only handles the simple case our generator produces (single hunk per file
    is not guaranteed; we always emit full-file diffs from difflib).
    """
    # Split diff into per-file blocks based on `--- ` headers.
    lines = diff.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if lines[i].startswith("--- "):
            from_file = lines[i][4:].strip()
            i += 1
            assert lines[i].startswith("+++ "), lines[i]
            i += 1
            new_lines: list[str] = []
            old_lines: list[str] = []
            # Read hunks until next file header or EOF.
            while i < len(lines) and not lines[i].startswith("--- "):
                line = lines[i]
                if line.startswith("@@"):
                    i += 1
                    continue
                if line.startswith("-"):
                    old_lines.append(line[1:])
                elif line.startswith("+"):
                    new_lines.append(line[1:])
                elif line.startswith(" "):
                    old_lines.append(line[1:])
                    new_lines.append(line[1:])
                i += 1
            target = root / from_file
            target.write_text("".join(new_lines))
        else:
            i += 1


def test_diff_round_trip_clears_missing_json(tmp_path: Path):
    src = FIXTURES / "plain-typer"
    dst = tmp_path / "plain-typer"
    shutil.copytree(src, dst)

    first = audit_project(dst, fix_dry_run=True)
    assert first.severity_max == "error"
    assert first.diff_preview is not None

    _apply_unified_diff(first.diff_preview, dst)

    # Confirm post-patch source still parses.
    cli = dst / "src" / "plain_typer" / "cli.py"
    ast.parse(cli.read_text())

    second = audit_project(dst)
    second_ids = {f.id for f in second.findings}
    # The diff fixes entry-point (warning) and signature (error) issues but
    # intentionally does NOT rewrite print() calls (still warning), so
    # severity_max drops from 'error' to 'warning'.
    assert "missing-json-flag" not in second_ids
    assert "app-uses-plain-typer" not in second_ids
    assert second.severity_max in (None, "info", "warning")
    assert second.severity_max != "error"
