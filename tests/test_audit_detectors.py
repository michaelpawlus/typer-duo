"""Tests for individual detectors and the audit walker integration."""

from __future__ import annotations

from pathlib import Path

from typer_duo.audit import audit_project

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def _ids(report) -> set[str]:
    return {f.id for f in report.findings}


def test_plain_typer_flags_missing_json_and_print():
    report = audit_project(FIXTURES / "plain-typer")
    ids = _ids(report)
    assert "missing-json-flag" in ids
    assert "bare-print-stdout" in ids
    assert "app-uses-plain-typer" in ids
    assert report.commands_total == 2
    assert report.commands_with_json == 0
    assert report.commands_using_print == 2
    assert report.severity_max == "error"
    assert report.score == 0
    assert report.entry_point.framework == "typer"


def test_duo_app_is_clean():
    report = audit_project(FIXTURES / "duo-typer")
    ids = _ids(report)
    assert "missing-json-flag" not in ids
    assert "app-uses-plain-typer" not in ids
    # duo fixture writes via duo_print + print to stderr, neither is bare-print-stdout
    assert "bare-print-stdout" not in ids
    assert report.commands_total == 2
    assert report.uses_duo_app
    assert report.score == 100


def test_mixed_flags_partial():
    report = audit_project(FIXTURES / "mixed")
    ids = _ids(report)
    # 'good' has --json, 'bad' does not — exactly one missing-json-flag finding
    missing_json = [f for f in report.findings if f.id == "missing-json-flag"]
    assert len(missing_json) == 1
    assert missing_json[0].command == "bad"
    # 'bad' uses plain print() and console.print() — should be flagged mixed-output-style
    assert "mixed-output-style" in ids
    # 'console = Console()' without stderr=True — should produce stderr-on-json-path or no-stderr-console
    assert "no-stderr-console" in ids or any(
        f.id == "stderr-on-json-path" for f in report.findings
    )
    assert report.commands_total == 2
    assert report.commands_with_json == 1
    assert report.commands_using_print == 1


def test_unknown_framework_when_no_entry_point(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'no-cli'\nversion = '0.0.0'\n"
    )
    report = audit_project(tmp_path)
    assert report.entry_point.framework == "unknown"
    assert report.commands_total == 0
    # No findings produced when there's no entry point.
    assert report.findings == []


def test_strict_severity_max_reflects_findings():
    plain = audit_project(FIXTURES / "plain-typer")
    duo = audit_project(FIXTURES / "duo-typer")
    assert plain.severity_max == "error"
    # duo fixture might still emit info-level findings; never error or warning
    assert duo.severity_max in (None, "info")


def test_to_dict_shape():
    report = audit_project(FIXTURES / "plain-typer")
    d = report.to_dict()
    assert set(d.keys()) >= {
        "audited_at",
        "path",
        "entry_point",
        "summary",
        "findings",
        "diff_preview",
    }
    assert d["entry_point"]["framework"] == "typer"
    assert "score" in d["summary"]
    assert "severity_max" in d["summary"]
