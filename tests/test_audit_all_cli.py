"""Tests for the `typer-duo audit-all` CLI surface."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from typer_duo.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "audit"
runner = CliRunner()


def _build_portfolio(tmp_path: Path) -> Path:
    """Stage a fake portfolio root from the audit fixtures."""
    root = tmp_path / "projects"
    root.mkdir()
    for name in ("duo-typer", "plain-typer", "mixed"):
        shutil.copytree(FIXTURES / name, root / name)
    # Project with no [project.scripts] table.
    nocli = root / "no-cli"
    nocli.mkdir()
    (nocli / "pyproject.toml").write_text(
        "[project]\nname='no-cli'\nversion='0.0.0'\n", encoding="utf-8"
    )
    return root


def test_audit_all_json_output_shape(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    result = runner.invoke(app, ["audit-all", "--root", str(root), "--json"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == 1
    assert payload["root"] == str(root)
    assert "generated_at" in payload
    names = {p["name"] for p in payload["projects"]}
    assert names == {"duo-typer", "plain-typer", "mixed", "no-cli"}

    by_name = {p["name"]: p for p in payload["projects"]}
    assert by_name["duo-typer"]["status"] == "ok"
    assert by_name["duo-typer"]["score"] == 1.0
    assert by_name["plain-typer"]["status"] == "fail"
    assert by_name["no-cli"]["status"] == "no-cli"
    assert by_name["no-cli"]["score"] is None
    assert "checks" not in by_name["no-cli"]

    assert payload["summary"]["total_projects"] == 4
    assert payload["summary"]["no_cli"] == 1
    assert payload["summary"]["passing"] >= 1
    assert payload["summary"]["failing"] >= 1
    assert 0.0 <= payload["portfolio_score"] <= 1.0


def test_audit_all_skip_no_cli(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    result = runner.invoke(
        app, ["audit-all", "--root", str(root), "--json", "--skip-no-cli"]
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {p["name"] for p in payload["projects"]}
    assert "no-cli" not in names
    assert payload["summary"]["no_cli"] == 0


def test_audit_all_include_filter(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    result = runner.invoke(
        app,
        [
            "audit-all", "--root", str(root), "--json",
            "--include", "duo-typer",
        ],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {p["name"] for p in payload["projects"]}
    assert names == {"duo-typer"}


def test_audit_all_human_output_writes_to_stderr(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    result = runner.invoke(app, ["audit-all", "--root", str(root)])
    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    assert "Portfolio root:" in result.stderr
    assert "portfolio_score" in result.stderr


def test_audit_all_output_writes_file(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    out = tmp_path / "scorecard.json"
    result = runner.invoke(
        app,
        ["audit-all", "--root", str(root), "--output", str(out)],
    )
    assert result.exit_code == 0, result.stderr
    assert out.is_file()
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == 1
    assert payload["projects"]


def test_audit_all_since_diff(tmp_path: Path):
    root = _build_portfolio(tmp_path)

    baseline = {
        "schema_version": 1,
        "generated_at": "2026-04-01T00:00:00Z",
        "root": str(root),
        "portfolio_score": 0.0,
        "projects": [
            {"name": "duo-typer", "score": 0.5, "status": "warn"},
            {"name": "departed", "score": 0.7, "status": "ok"},
        ],
        "summary": {},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))

    result = runner.invoke(
        app,
        ["audit-all", "--root", str(root), "--json", "--since", str(baseline_path)],
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    diff = payload["diff"]
    assert diff["vs_baseline"] == "2026-04-01T00:00:00Z"
    assert "duo-typer" in diff["improved"]
    assert "departed" in diff["removed"]
    assert "plain-typer" in diff["newly_added"]


def test_audit_all_fail_under_triggers_exit_code(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    # Portfolio includes plain-typer which scores 0, so portfolio < 0.99.
    result = runner.invoke(
        app,
        [
            "audit-all", "--root", str(root), "--json",
            "--fail-under", "0.99",
        ],
    )
    assert result.exit_code == 1


def test_audit_all_fail_under_passes_when_above_threshold(tmp_path: Path):
    root = _build_portfolio(tmp_path)
    result = runner.invoke(
        app,
        [
            "audit-all", "--root", str(root), "--json",
            "--include", "duo-typer",
            "--fail-under", "0.99",
        ],
    )
    assert result.exit_code == 0, result.stderr


def test_audit_all_empty_root_returns_clean_scorecard(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["audit-all", "--root", str(empty), "--json"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["projects"] == []
    assert payload["portfolio_score"] is None
    assert payload["summary"]["total_projects"] == 0
