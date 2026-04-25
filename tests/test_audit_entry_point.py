"""Tests for entry-point detection."""

from __future__ import annotations

from pathlib import Path

from typer_duo.audit.entry_point import detect_entry_point

FIXTURES = Path(__file__).parent / "fixtures" / "audit"


def test_detects_plain_typer_entry_point():
    ep = detect_entry_point(FIXTURES / "plain-typer")
    assert ep.framework == "typer"
    assert ep.module == "plain_typer.cli"
    assert ep.app_var == "app"
    assert ep.script_name == "plain-typer"


def test_detects_duo_app_entry_point():
    ep = detect_entry_point(FIXTURES / "duo-typer")
    assert ep.framework == "duo"
    assert ep.module == "duo_typer.cli"
    assert ep.app_var == "app"


def test_detects_mixed_entry_point():
    ep = detect_entry_point(FIXTURES / "mixed")
    assert ep.framework == "typer"
    assert ep.app_var == "app"


def test_returns_unknown_for_non_typer_dir(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\nversion = '0.0.0'\n")
    ep = detect_entry_point(tmp_path)
    assert ep.framework == "unknown"
    assert ep.module is None


def test_falls_back_to_cli_py_without_pyproject(tmp_path: Path):
    cli = tmp_path / "cli.py"
    cli.write_text("import typer\napp = typer.Typer()\n")
    ep = detect_entry_point(tmp_path)
    assert ep.framework == "typer"
    assert ep.app_var == "app"
