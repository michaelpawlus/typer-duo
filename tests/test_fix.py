"""Tests for the `typer-duo fix` subcommand (closes the audit loop)."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from typer_duo.audit import audit_project
from typer_duo.cli import app
from typer_duo.fixers import (
    DEFAULT_FIXERS,
    FIXERS,
    OPT_IN_FIXERS,
    add_json_flag,
    add_project_script_entry,
    migrate_to_duoapp,
    replace_print_with_stderr,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audit"
runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def plain_typer_copy(tmp_path: Path) -> Path:
    """Copy the plain-typer fixture into tmp_path so tests can mutate it."""
    dst = tmp_path / "plain-typer"
    shutil.copytree(FIXTURES / "plain-typer", dst)
    return dst


@pytest.fixture
def duo_typer_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "duo-typer"
    shutil.copytree(FIXTURES / "duo-typer", dst)
    return dst


@pytest.fixture
def no_scripts_project(tmp_path: Path) -> Path:
    """A Typer project whose pyproject.toml has no [project.scripts] table."""
    root = tmp_path / "no-scripts"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'no-scripts'\nversion = '0.0.0'\n",
        encoding="utf-8",
    )
    (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "pkg" / "cli.py").write_text(
        '"""CLI."""\nimport typer\napp = typer.Typer()\n@app.command()\ndef hi() -> None:\n    print("hi")\n',
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_registry_lists_known_fixers():
    expected = {
        "add-json-flag",
        "replace-print-with-stderr",
        "add-project-script-entry",
        "migrate-to-duoapp",
    }
    assert set(FIXERS) == expected
    assert "migrate-to-duoapp" in OPT_IN_FIXERS
    assert "migrate-to-duoapp" not in DEFAULT_FIXERS
    assert set(DEFAULT_FIXERS).isdisjoint(OPT_IN_FIXERS)


# ---------------------------------------------------------------------------
# Individual fixers (golden assertions about diffs / outputs)
# ---------------------------------------------------------------------------


def test_add_json_flag_proposes_edit(plain_typer_copy: Path):
    report = audit_project(plain_typer_copy)
    result = add_json_flag.propose(plain_typer_copy, report)
    assert result.status == "proposed"
    assert "missing-json-flag" in result.findings_addressed
    assert len(result.edits) == 1

    edit = result.edits[0]
    assert edit.path == "src/plain_typer/cli.py"
    assert "json_output: JsonFlag = False" in edit.updated
    assert "from typer_duo import" in edit.updated
    # Post-fix source must still parse.
    ast.parse(edit.updated)


def test_add_json_flag_is_idempotent(duo_typer_copy: Path):
    report = audit_project(duo_typer_copy)
    result = add_json_flag.propose(duo_typer_copy, report)
    assert result.status == "no-op"


def test_replace_print_with_stderr_proposes_edit(plain_typer_copy: Path):
    report = audit_project(plain_typer_copy)
    result = replace_print_with_stderr.propose(plain_typer_copy, report)
    assert result.status == "proposed"
    assert "bare-print-stdout" in result.findings_addressed
    assert len(result.edits) == 1

    edit = result.edits[0]
    assert "file=sys.stderr" in edit.updated
    assert "import sys" in edit.updated
    # Both print calls should have been rewritten.
    assert edit.updated.count("file=sys.stderr") == 2
    ast.parse(edit.updated)


def test_replace_print_with_stderr_skips_already_redirected(duo_typer_copy: Path):
    # duo-typer already does `print("about to check", file=sys.stderr)`,
    # so the fixer should make no edits.
    report = audit_project(duo_typer_copy)
    result = replace_print_with_stderr.propose(duo_typer_copy, report)
    assert result.status == "no-op"


def test_migrate_to_duoapp_proposes_edit(plain_typer_copy: Path):
    report = audit_project(plain_typer_copy)
    result = migrate_to_duoapp.propose(plain_typer_copy, report)
    assert result.status == "proposed"
    assert "app-uses-plain-typer" in result.findings_addressed

    edit = result.edits[0]
    assert "DuoApp(name=\"plain-typer\")" in edit.updated
    assert "from typer_duo import" in edit.updated
    ast.parse(edit.updated)


def test_migrate_to_duoapp_is_noop_on_duo_project(duo_typer_copy: Path):
    report = audit_project(duo_typer_copy)
    result = migrate_to_duoapp.propose(duo_typer_copy, report)
    assert result.status == "no-op"


def test_add_project_script_entry_adds_entry(no_scripts_project: Path):
    report = audit_project(no_scripts_project)
    # Audit should still find the Typer app via fallback scan.
    assert report.entry_point.framework == "typer"
    assert report.entry_point.script_name is None

    result = add_project_script_entry.propose(no_scripts_project, report)
    assert result.status == "proposed"
    assert len(result.edits) == 1

    edit = result.edits[0]
    assert edit.path == "pyproject.toml"
    assert "[project.scripts]" in edit.updated
    assert "pkg.cli:app" in edit.updated


def test_add_project_script_entry_noop_when_present(plain_typer_copy: Path):
    report = audit_project(plain_typer_copy)
    result = add_project_script_entry.propose(plain_typer_copy, report)
    assert result.status == "no-op"


def test_add_project_script_entry_skip_on_name_collision(no_scripts_project: Path):
    # Pre-create a [project.scripts] section that uses the slug but maps elsewhere.
    py = no_scripts_project / "pyproject.toml"
    py.write_text(
        py.read_text()
        + '\n[project.scripts]\nno-scripts = "other.cli:app"\n',
        encoding="utf-8",
    )
    report = audit_project(no_scripts_project)
    result = add_project_script_entry.propose(no_scripts_project, report)
    assert result.status == "skipped"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_fix_dry_run_emits_diff_to_stdout(plain_typer_copy: Path):
    res = runner.invoke(
        app, ["fix", str(plain_typer_copy), "--dry-run"]
    )
    assert res.exit_code == 0, res.stderr
    # Diff hunk markers should appear in stdout (human mode).
    assert "--- a/src/plain_typer/cli.py" in res.stdout
    assert "+++ b/src/plain_typer/cli.py" in res.stdout
    # File on disk is untouched.
    assert "json_output" not in (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()


def test_fix_dry_run_does_not_write(plain_typer_copy: Path):
    before = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    runner.invoke(app, ["fix", str(plain_typer_copy), "--dry-run"])
    after = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    assert before == after


def test_fix_apply_writes_changes_and_clears_findings(plain_typer_copy: Path):
    res = runner.invoke(app, ["fix", str(plain_typer_copy)])
    assert res.exit_code == 0, res.stderr

    new_source = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    assert "json_output: JsonFlag = False" in new_source
    assert "file=sys.stderr" in new_source

    # Re-audit: the two findings the default fixers address should be gone.
    second = audit_project(plain_typer_copy)
    finding_ids = {f.id for f in second.findings}
    assert "missing-json-flag" not in finding_ids
    assert "bare-print-stdout" not in finding_ids


def test_fix_apply_is_idempotent(plain_typer_copy: Path):
    runner.invoke(app, ["fix", str(plain_typer_copy)])
    first = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    res = runner.invoke(app, ["fix", str(plain_typer_copy)])
    assert res.exit_code == 0
    second = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    assert first == second


def test_fix_check_filter_runs_only_specified(plain_typer_copy: Path):
    res = runner.invoke(
        app,
        ["fix", str(plain_typer_copy), "--check", "add-json-flag", "--json"],
    )
    assert res.exit_code == 0, res.stderr
    payload = json.loads(res.stdout)
    fixer_ids_seen = {
        e["fixer_id"]
        for e in payload["applied"] + payload["skipped"] + payload["errors"]
    }
    assert fixer_ids_seen == {"add-json-flag"}


def test_fix_unknown_check_returns_error(plain_typer_copy: Path):
    res = runner.invoke(
        app,
        ["fix", str(plain_typer_copy), "--check", "not-a-real-fixer", "--json"],
    )
    assert res.exit_code == 1
    payload = json.loads(res.stdout)
    assert "unknown" in payload["error"]


def test_fix_no_entry_point_returns_2(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\nversion = '0.0.0'\n", encoding="utf-8"
    )
    res = runner.invoke(app, ["fix", str(tmp_path), "--json"])
    assert res.exit_code == 2
    payload = json.loads(res.stdout)
    assert payload["error"] == "no Typer entry point detected"


def test_fix_migrate_to_duoapp_only_runs_when_requested(plain_typer_copy: Path):
    # Default run must not touch the entry-point class.
    runner.invoke(app, ["fix", str(plain_typer_copy)])
    src = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    assert "DuoApp(" not in src
    assert "typer.Typer(" in src

    # Explicit opt-in does flip it.
    res = runner.invoke(
        app,
        ["fix", str(plain_typer_copy), "--check", "migrate-to-duoapp"],
    )
    assert res.exit_code == 0, res.stderr
    src2 = (plain_typer_copy / "src" / "plain_typer" / "cli.py").read_text()
    assert "DuoApp(" in src2


def test_fix_json_payload_shape(plain_typer_copy: Path):
    res = runner.invoke(
        app, ["fix", str(plain_typer_copy), "--dry-run", "--json"]
    )
    assert res.exit_code == 0, res.stderr
    payload = json.loads(res.stdout)
    assert set(payload) == {"dry_run", "applied", "skipped", "errors"}
    assert payload["dry_run"] is True
    # Two default fixers have proposed edits in this fixture.
    assert len(payload["applied"]) == 2
    for entry in payload["applied"]:
        assert entry["fixer_id"] in DEFAULT_FIXERS
        assert "diff" in entry
        assert entry["diff"].startswith("--- a/")
    # The third default fixer (add-project-script-entry) is a no-op here.
    skipped_ids = {e["fixer_id"] for e in payload["skipped"]}
    assert "add-project-script-entry" in skipped_ids


def test_fix_consistent_with_audit_dry_run_diff(plain_typer_copy: Path):
    """The fix command + audit --fix-dry-run must not drift.

    Both should agree on adding ``json_output: JsonFlag = False`` and on
    DuoApp migration when migrate-to-duoapp runs.
    """
    audit_report = audit_project(plain_typer_copy, fix_dry_run=True)
    diff = audit_report.diff_preview or ""

    # add-json-flag's edit should match the audit preview's signature insert.
    fix_result = add_json_flag.propose(plain_typer_copy, audit_report)
    fix_text = fix_result.edits[0].updated
    assert "json_output: JsonFlag = False" in fix_text
    assert "json_output: JsonFlag = False" in diff

    # migrate-to-duoapp's edit must agree on the DuoApp(...) rewrite.
    migrate_result = migrate_to_duoapp.propose(plain_typer_copy, audit_report)
    migrate_text = migrate_result.edits[0].updated
    assert "DuoApp(name=\"plain-typer\")" in migrate_text
    assert "DuoApp(name=\"plain-typer\")" in diff
