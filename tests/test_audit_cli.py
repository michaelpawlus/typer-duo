"""Tests for the `typer-duo audit` CLI surface."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from typer_duo.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "audit"
runner = CliRunner()


def test_audit_json_output_shape():
    result = runner.invoke(
        app, ["audit", str(FIXTURES / "plain-typer"), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["entry_point"]["framework"] == "typer"
    assert payload["summary"]["commands_total"] == 2
    assert payload["summary"]["severity_max"] == "error"
    assert payload["summary"]["score"] == 0


def test_audit_strict_returns_error_on_findings():
    result = runner.invoke(
        app, ["audit", str(FIXTURES / "plain-typer"), "--json", "--strict"]
    )
    assert result.exit_code == 1


def test_audit_strict_clean_project_exits_zero():
    result = runner.invoke(
        app, ["audit", str(FIXTURES / "duo-typer"), "--json", "--strict"]
    )
    assert result.exit_code == 0


def test_audit_returns_2_when_no_entry_point(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\nversion = '0.0.0'\n"
    )
    result = runner.invoke(app, ["audit", str(tmp_path), "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["error"] == "no Typer entry point detected"
    assert payload["code"] == 2


def test_audit_human_output_writes_to_stderr():
    result = runner.invoke(app, ["audit", str(FIXTURES / "plain-typer")])
    assert result.exit_code == 0
    # JSON-style payload should NOT be on stdout in human mode.
    assert result.stdout.strip() == ""
    assert "Audited:" in result.stderr


def test_audit_self_dogfood_score_100():
    """typer-duo auditing itself should score 100."""
    project_root = Path(__file__).parent.parent
    result = runner.invoke(
        app,
        ["audit", str(project_root), "--json", "--exclude", "tests/fixtures/*"],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["entry_point"]["framework"] == "duo"
    assert payload["summary"]["score"] == 100
