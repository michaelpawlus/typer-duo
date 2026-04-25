"""Scaffold command for generating new typer-duo projects."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..app import DuoApp

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    Environment = None  # type: ignore[assignment, misc]
    FileSystemLoader = None  # type: ignore[assignment, misc]

app = DuoApp(name="typer-duo", help="Scaffold new typer-duo CLI projects.")

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _render_template(env: Environment, template_name: str, context: dict) -> str:  # type: ignore[type-arg]
    template = env.get_template(template_name)
    return template.render(**context)


@app.command(duo=False)
def init(
    project_name: str = typer.Argument(help="Name of the new CLI project"),
    description: Optional[str] = typer.Option(
        None, "--description", help="One-line project description"
    ),
    author: Optional[str] = typer.Option(
        None, "--author", help="Author name for pyproject.toml"
    ),
    no_tests: bool = typer.Option(False, "--no-tests", help="Skip test skeleton"),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o", help="Parent directory for the project (default: current dir)"
    ),
) -> None:
    """Generate a new CLI project pre-wired with typer-duo patterns."""
    if Environment is None:
        typer.echo("Error: jinja2 is required for scaffolding. Install with: pip install typer-duo[scaffold]", err=True)
        raise typer.Exit(1)

    module_name = project_name.replace("-", "_")
    desc = description or f"CLI tool: {project_name}"

    context = {
        "project_name": project_name,
        "module_name": module_name,
        "description": desc,
        "author": author or "",
    }

    parent = Path(output_dir) if output_dir else Path.cwd()
    project_dir = parent / project_name
    if project_dir.exists():
        typer.echo(f"Error: directory '{project_dir}' already exists", err=True)
        raise typer.Exit(1)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), keep_trailing_newline=True)

    # Create directory structure
    src_dir = project_dir / "src" / module_name
    src_dir.mkdir(parents=True)

    # Render and write files
    files: list[tuple[Path, str]] = [
        (project_dir / "pyproject.toml", _render_template(env, "pyproject.toml.j2", context)),
        (src_dir / "__init__.py", _render_template(env, "src/__init__.py.j2", context)),
        (src_dir / "cli.py", _render_template(env, "src/cli.py.j2", context)),
        (project_dir / "CLAUDE.md", _render_template(env, "CLAUDE.md.j2", context)),
    ]

    if not no_tests:
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(parents=True)
        files.append(
            (tests_dir / "test_cli.py", _render_template(env, "tests/test_cli.py.j2", context))
        )

    for file_path, content in files:
        file_path.write_text(content)

    typer.echo(f"Created project: {project_dir}", err=True)
    typer.echo(f"  cd {project_name} && python -m venv .venv && .venv/bin/pip install -e '.[dev]'", err=True)
