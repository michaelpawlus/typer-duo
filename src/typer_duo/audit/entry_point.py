"""Entry-point detection for audit targets.

Reads a project's pyproject.toml [project.scripts] table to find a Typer-based
entry point, falling back to common conventions (cli.py / src/*/cli.py).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from .models import EntryPoint


def _resolve_module_path(project_root: Path, module: str) -> Path | None:
    """Resolve a dotted module name to a .py file inside *project_root*.

    Tries both ``module.py`` directly and ``src/module.py`` layouts.
    """
    parts = module.split(".")
    candidates = [
        project_root.joinpath(*parts).with_suffix(".py"),
        project_root.joinpath(*parts) / "__init__.py",
        project_root / "src" / Path(*parts).with_suffix(".py"),
        project_root / "src" / Path(*parts) / "__init__.py",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _detect_app_in_module(module_file: Path, app_var: str) -> tuple[bool, str]:
    """Inspect a module's AST to determine if *app_var* is a Typer/DuoApp.

    Returns (is_typer_based, framework) where framework is "typer" | "duo" | "unknown".
    """
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return False, "unknown"

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == app_var:
                    return _classify_call(node.value)
    return False, "unknown"


def _classify_call(value: ast.expr) -> tuple[bool, str]:
    """Classify an assignment RHS as DuoApp / typer.Typer / unknown."""
    if not isinstance(value, ast.Call):
        return False, "unknown"
    func = value.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name == "DuoApp":
        return True, "duo"
    if name == "Typer":
        return True, "typer"
    return False, "unknown"


def _scan_for_typer_module(project_root: Path) -> tuple[Path, str, str] | None:
    """Walk the project for a module that defines ``app = typer.Typer(...)`` or DuoApp.

    Returns (file, dotted_module, app_var) or None.
    """
    candidates: list[Path] = []
    cli_root = project_root / "cli.py"
    if cli_root.is_file():
        candidates.append(cli_root)
    src = project_root / "src"
    if src.is_dir():
        candidates.extend(sorted(src.rglob("cli.py")))
    # Also consider any package __init__.py with a Typer app defined.
    if src.is_dir():
        candidates.extend(sorted(src.rglob("__init__.py")))

    for path in candidates:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        is_typer, _framework = _classify_call(node.value)
                        if is_typer:
                            module = _path_to_module(project_root, path)
                            return path, module, target.id
    return None


def _path_to_module(project_root: Path, path: Path) -> str:
    """Convert a file path to a dotted module name relative to project_root.

    Handles both top-level and src/ layouts. Strips __init__ suffix.
    """
    rel = path.resolve().relative_to(project_root.resolve())
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def detect_entry_point(project_root: Path) -> EntryPoint:
    """Detect the Typer entry point for a project.

    Strategy:
    1. Read pyproject.toml [project.scripts]; for each "module:var" target,
       resolve the module locally and pick the first one whose target var
       resolves to a Typer/DuoApp call.
    2. Fall back to scanning cli.py / src/**/cli.py.
    3. Return EntryPoint(framework="unknown") if nothing found.
    """
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            data = {}
        scripts = data.get("project", {}).get("scripts", {}) or {}
        for script_name, target in scripts.items():
            if not isinstance(target, str) or ":" not in target:
                continue
            module, _, app_var = target.partition(":")
            module_file = _resolve_module_path(project_root, module)
            if module_file is None:
                continue
            is_typer, framework = _detect_app_in_module(module_file, app_var)
            if is_typer:
                return EntryPoint(
                    script_name=script_name,
                    module=module,
                    app_var=app_var,
                    framework=framework,
                    file=str(module_file),
                )

    # Fall back to scanning for a Typer app in conventional locations.
    found = _scan_for_typer_module(project_root)
    if found is not None:
        path, module, app_var = found
        is_typer, framework = _detect_app_in_module(path, app_var)
        if is_typer:
            return EntryPoint(
                script_name=None,
                module=module,
                app_var=app_var,
                framework=framework,
                file=str(path),
            )

    return EntryPoint(
        script_name=None, module=None, app_var=None, framework="unknown"
    )
