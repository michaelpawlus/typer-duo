"""Tests for typer_duo.discovery."""

from __future__ import annotations

from pathlib import Path

from typer_duo.discovery import iter_projects


def _write_pyproject(d: Path, name: str, scripts: dict[str, str] | None = None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    lines = ["[project]", f'name = "{name}"', 'version = "0.0.0"']
    if scripts:
        lines.append("")
        lines.append("[project.scripts]")
        for k, v in scripts.items():
            lines.append(f'{k} = "{v}"')
    (d / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_iter_projects_returns_only_pyproject_dirs(tmp_path: Path):
    _write_pyproject(tmp_path / "alpha", "alpha", {"alpha": "a:app"})
    _write_pyproject(tmp_path / "beta", "beta")  # has pyproject, no scripts
    (tmp_path / "no_pyproject").mkdir()
    (tmp_path / "no_pyproject" / "README.md").write_text("hi")

    found = {p.name: p for p in iter_projects(tmp_path)}

    assert set(found) == {"alpha", "beta"}
    assert found["alpha"].has_scripts is True
    assert found["alpha"].scripts == ("alpha",)
    assert found["beta"].has_scripts is False
    assert found["beta"].scripts == ()


def test_iter_projects_skips_hidden_dirs(tmp_path: Path):
    _write_pyproject(tmp_path / ".venv", "venv", {"x": "x:app"})
    _write_pyproject(tmp_path / "real", "real", {"x": "x:app"})

    names = {p.name for p in iter_projects(tmp_path)}
    assert names == {"real"}


def test_iter_projects_include_exclude(tmp_path: Path):
    for n in ("alpha", "beta", "gamma"):
        _write_pyproject(tmp_path / n, n, {n: f"{n}:app"})

    only_a = {p.name for p in iter_projects(tmp_path, include=["a*"])}
    assert only_a == {"alpha"}

    not_b = {p.name for p in iter_projects(tmp_path, exclude=["beta"])}
    assert not_b == {"alpha", "gamma"}


def test_iter_projects_handles_malformed_pyproject(tmp_path: Path):
    proj = tmp_path / "broken"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("not = valid = toml [[", encoding="utf-8")

    found = list(iter_projects(tmp_path))
    assert len(found) == 1
    assert found[0].name == "broken"
    assert found[0].has_scripts is False
