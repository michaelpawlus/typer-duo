"""Tests for typer_duo.scorecard."""

from __future__ import annotations

from pathlib import Path

from typer_duo.audit import audit_project
from typer_duo.scorecard import (
    SCHEMA_VERSION,
    build_scorecard,
    compute_diff,
    no_cli_score,
    score_from_report,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def test_score_from_report_clean_duo_project():
    report = audit_project(FIXTURES / "duo-typer")
    score = score_from_report("duo-typer", str(FIXTURES / "duo-typer"), report)

    assert score.status == "ok"
    assert score.score == 1.0
    assert score.checks["json_flag_parity"] == "pass"
    assert score.checks["duo_registered"] == "pass"
    assert score.commands_failing == []


def test_score_from_report_failing_plain_project():
    report = audit_project(FIXTURES / "plain-typer")
    score = score_from_report("plain-typer", str(FIXTURES / "plain-typer"), report)

    assert score.status == "fail"
    assert score.score is not None and score.score <= 0.5
    assert score.checks["json_flag_parity"] == "fail"
    assert score.checks["duo_registered"] == "warn"
    assert score.commands_failing  # at least one


def test_score_from_report_non_typer(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\nversion='0.0.0'\n[project.scripts]\nx='x:cli'\n"
    )
    report = audit_project(tmp_path)
    score = score_from_report("x", str(tmp_path), report)
    assert score.status == "non-typer"
    assert score.score is None


def test_no_cli_score_serialization():
    s = no_cli_score("foo", "/tmp/foo").to_dict()
    assert s["status"] == "no-cli"
    assert s["score"] is None
    assert "checks" not in s
    assert "commands_audited" not in s


def test_build_scorecard_summary_and_portfolio_score():
    duo_report = audit_project(FIXTURES / "duo-typer")
    plain_report = audit_project(FIXTURES / "plain-typer")
    projects = [
        score_from_report("duo-typer", str(FIXTURES / "duo-typer"), duo_report),
        score_from_report("plain-typer", str(FIXTURES / "plain-typer"), plain_report),
        no_cli_score("nocli", "/tmp/nocli"),
    ]

    sc = build_scorecard(root="/tmp", projects=projects)
    payload = sc.to_dict()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["summary"]["total_projects"] == 3
    assert payload["summary"]["with_cli"] == 2
    assert payload["summary"]["no_cli"] == 1
    assert payload["summary"]["passing"] == 1
    assert payload["summary"]["failing"] == 1
    # Portfolio score = mean of (1.0, ~0) ≈ 0.5
    assert 0.0 <= payload["portfolio_score"] <= 1.0
    assert payload["portfolio_score"] == round((1.0 + projects[1].score) / 2, 2)


def test_build_scorecard_empty_root():
    sc = build_scorecard(root="/tmp", projects=[])
    payload = sc.to_dict()
    assert payload["projects"] == []
    assert payload["portfolio_score"] is None
    assert payload["summary"]["total_projects"] == 0


def test_compute_diff_detects_movement():
    baseline = {
        "generated_at": "2026-04-22T00:00:00Z",
        "projects": [
            {"name": "a", "score": 0.50},
            {"name": "b", "score": 1.00},
            {"name": "removed", "score": 0.80},
        ],
    }
    current = {
        "generated_at": "2026-05-06T00:00:00Z",
        "projects": [
            {"name": "a", "score": 0.80},   # improved
            {"name": "b", "score": 0.60},   # regressed
            {"name": "newcomer", "score": 0.90},  # newly_added
        ],
    }
    diff = compute_diff(current, baseline)
    assert diff["vs_baseline"] == "2026-04-22T00:00:00Z"
    assert diff["improved"] == ["a"]
    assert diff["regressed"] == ["b"]
    assert diff["newly_added"] == ["newcomer"]
    assert diff["removed"] == ["removed"]


def test_compute_diff_ignores_null_scores():
    baseline = {
        "generated_at": "2026-04-22T00:00:00Z",
        "projects": [{"name": "a", "score": None}],
    }
    current = {
        "generated_at": "2026-05-06T00:00:00Z",
        "projects": [{"name": "a", "score": 0.5}],
    }
    diff = compute_diff(current, baseline)
    assert diff["improved"] == []
    assert diff["regressed"] == []
