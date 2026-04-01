"""Tests for the scaffold command."""

import os
from pathlib import Path

from typer.testing import CliRunner

from typer_duo.scaffold import app

runner = CliRunner()


def test_scaffold_creates_project(tmp_path):
    result = runner.invoke(app, ["my-tool", "-o", str(tmp_path)])
    assert result.exit_code == 0

    project_dir = tmp_path / "my-tool"
    assert project_dir.is_dir()

    # Check file structure
    assert (project_dir / "pyproject.toml").is_file()
    assert (project_dir / "CLAUDE.md").is_file()
    assert (project_dir / "src" / "my_tool" / "__init__.py").is_file()
    assert (project_dir / "src" / "my_tool" / "cli.py").is_file()
    assert (project_dir / "tests" / "test_cli.py").is_file()


def test_scaffold_pyproject_content(tmp_path):
    result = runner.invoke(
        app,
        ["my-tool", "-o", str(tmp_path), "--description", "A test tool", "--author", "Test Author"],
    )
    assert result.exit_code == 0

    content = (tmp_path / "my-tool" / "pyproject.toml").read_text()
    assert 'name = "my-tool"' in content
    assert '"A test tool"' in content
    assert '"Test Author"' in content
    assert "typer-duo" in content


def test_scaffold_cli_content(tmp_path):
    result = runner.invoke(app, ["my-tool", "-o", str(tmp_path)])
    assert result.exit_code == 0

    cli_content = (tmp_path / "my-tool" / "src" / "my_tool" / "cli.py").read_text()
    assert "DuoApp" in cli_content
    assert "my-tool" in cli_content
    assert "hello" in cli_content


def test_scaffold_no_tests(tmp_path):
    result = runner.invoke(app, ["my-tool", "-o", str(tmp_path), "--no-tests"])
    assert result.exit_code == 0

    project_dir = tmp_path / "my-tool"
    assert not (project_dir / "tests").exists()


def test_scaffold_claude_md(tmp_path):
    result = runner.invoke(app, ["my-tool", "-o", str(tmp_path)])
    assert result.exit_code == 0

    claude_md = (tmp_path / "my-tool" / "CLAUDE.md").read_text()
    assert "my-tool" in claude_md
    assert "--json" in claude_md


def test_scaffold_existing_dir_fails(tmp_path):
    (tmp_path / "my-tool").mkdir()
    result = runner.invoke(app, ["my-tool", "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_scaffold_hyphenated_name_to_underscore(tmp_path):
    result = runner.invoke(app, ["my-cool-tool", "-o", str(tmp_path)])
    assert result.exit_code == 0

    assert (tmp_path / "my-cool-tool" / "src" / "my_cool_tool" / "cli.py").is_file()
