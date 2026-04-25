"""Walk a project's source files, find Typer commands, run detectors."""

from __future__ import annotations

import ast
import datetime as dt
import fnmatch
from pathlib import Path

from .detectors import (
    CommandInfo,
    detect_app_uses_plain_typer,
    detect_no_stderr_console,
    run_per_command_detectors,
)
from .entry_point import detect_entry_point
from .models import AuditReport, EntryPoint, Finding


def _files_to_scan(
    project_root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
) -> list[Path]:
    """Collect .py files under src/ + top-level cli.py, filtered by globs."""
    candidates: list[Path] = []
    src = project_root / "src"
    if src.is_dir():
        candidates.extend(sorted(src.rglob("*.py")))
    cli_root = project_root / "cli.py"
    if cli_root.is_file():
        candidates.append(cli_root)

    # If src/ does not exist, fall back to a shallow scan of *.py at root.
    if not src.is_dir() and not cli_root.is_file():
        candidates.extend(sorted(project_root.glob("*.py")))

    rels = [c.resolve().relative_to(project_root.resolve()) for c in candidates]

    def matches_any(rel: Path, patterns: list[str]) -> bool:
        rel_str = str(rel).replace("\\", "/")
        return any(fnmatch.fnmatch(rel_str, p) for p in patterns)

    out: list[Path] = []
    for c, rel in zip(candidates, rels):
        if include and not matches_any(rel, include):
            continue
        if exclude and matches_any(rel, exclude):
            continue
        out.append(c)
    return out


def _is_app_command_decorator(
    decorator: ast.expr, app_vars: set[str]
) -> str | None:
    """If *decorator* matches ``<app>.command(...)``, return ``<app>``.

    Accepts both ``@app.command()`` and ``@app.command``.
    """
    target: ast.expr = decorator
    if isinstance(decorator, ast.Call):
        target = decorator.func
    if isinstance(target, ast.Attribute) and target.attr == "command":
        if isinstance(target.value, ast.Name) and target.value.id in app_vars:
            return target.value.id
    return None


def _module_app_vars(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """Find module-level Typer/DuoApp instances.

    Returns:
        (app_var_to_framework, duo_app_vars)
        where framework is "typer" | "duo".
    """
    var_to_framework: dict[str, str] = {}
    duo_vars: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                    func = node.value.func
                    name = None
                    if isinstance(func, ast.Name):
                        name = func.id
                    elif isinstance(func, ast.Attribute):
                        name = func.attr
                    if name == "DuoApp":
                        var_to_framework[target.id] = "duo"
                        duo_vars.add(target.id)
                    elif name == "Typer":
                        var_to_framework[target.id] = "typer"
    return var_to_framework, duo_vars


def _find_commands(
    tree: ast.Module, file: Path, project_root: Path
) -> tuple[list[CommandInfo], set[str], dict[str, str]]:
    """Discover all Typer commands in *tree* with their owning app's framework."""
    var_to_framework, duo_vars = _module_app_vars(tree)
    app_vars = set(var_to_framework.keys())
    commands: list[CommandInfo] = []
    rel = str(file.resolve().relative_to(project_root.resolve()))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                app_var = _is_app_command_decorator(dec, app_vars)
                if app_var is None:
                    continue
                commands.append(
                    CommandInfo(
                        name=node.name,
                        func_node=node,
                        file=str(file),
                        relative_file=rel,
                        decorator_app_var=app_var,
                        is_on_duo_app=app_var in duo_vars,
                    )
                )
                break
    return commands, duo_vars, var_to_framework


def _command_uses_print(cmd: CommandInfo) -> bool:
    for n in ast.walk(cmd.func_node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "print"
        ):
            for kw in n.keywords:
                if kw.arg == "file":
                    target = kw.value
                    if (
                        isinstance(target, ast.Attribute) and target.attr == "stderr"
                    ) or (isinstance(target, ast.Name) and target.id == "stderr"):
                        break
            else:
                return True
    return False


def _command_uses_duo_print(cmd: CommandInfo) -> bool:
    for n in ast.walk(cmd.func_node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id == "duo_print":
                return True
    return False


def _command_has_json(cmd: CommandInfo) -> bool:
    if cmd.is_on_duo_app:
        return True
    from .detectors import _arg_has_json_param  # local to avoid cycles

    return _arg_has_json_param(cmd.func_node)


def audit_project(
    project_root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    *,
    fix_dry_run: bool = False,
) -> AuditReport:
    """Run the audit over *project_root* and return a structured report."""
    entry = detect_entry_point(project_root)
    audited_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = AuditReport(
        audited_at=audited_at,
        path=str(project_root.resolve()),
        entry_point=entry,
    )

    if entry.framework == "unknown":
        return report

    files = _files_to_scan(project_root, include, exclude)

    findings: list[Finding] = []
    all_commands: list[CommandInfo] = []
    saw_duo_app = False
    plain_typer_apps: list[tuple[str, int]] = []  # (file, lineno)

    has_stderr_console_anywhere = False

    for file in files:
        try:
            source = file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue
        rel = str(file.resolve().relative_to(project_root.resolve()))

        var_to_framework, duo_vars = _module_app_vars(tree)
        if duo_vars:
            saw_duo_app = True
        for var, fw in var_to_framework.items():
            if fw == "typer":
                # Find the lineno of the assignment for diff/finding purposes.
                lineno = _find_assignment_lineno(tree, var) or 1
                plain_typer_apps.append((rel, lineno))

        # Track whether any module has Console(stderr=True).
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and (
                    (isinstance(n.func, ast.Name) and n.func.id == "Console")
                    or (
                        isinstance(n.func, ast.Attribute)
                        and n.func.attr == "Console"
                    )
                )
            ):
                for kw in n.keywords:
                    if (
                        kw.arg == "stderr"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value
                    ):
                        has_stderr_console_anywhere = True

        commands, _, _ = _find_commands(tree, file, project_root)
        all_commands.extend(commands)
        for cmd in commands:
            findings.extend(run_per_command_detectors(cmd))

    # Top-level findings.
    if entry.framework == "typer":
        # Prefer the entry-point file itself.
        ep_file = entry.file
        if ep_file:
            try:
                ep_rel = str(
                    Path(ep_file).resolve().relative_to(project_root.resolve())
                )
            except ValueError:
                ep_rel = ep_file
            ep_lineno = _find_assignment_lineno_in_file(Path(ep_file), entry.app_var or "app") or 1
            findings.extend(detect_app_uses_plain_typer(entry.framework, ep_rel, ep_lineno))

    if not has_stderr_console_anywhere and entry.file:
        try:
            ep_rel = str(Path(entry.file).resolve().relative_to(project_root.resolve()))
        except ValueError:
            ep_rel = entry.file
        try:
            ep_tree = ast.parse(Path(entry.file).read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            ep_tree = None
        if ep_tree is not None:
            findings.extend(detect_no_stderr_console(ep_tree, ep_rel))

    # Roll up summary stats.
    commands_total = len(all_commands)
    commands_with_json = sum(1 for c in all_commands if _command_has_json(c))
    commands_using_print = sum(1 for c in all_commands if _command_uses_print(c))
    commands_with_duo_print = sum(1 for c in all_commands if _command_uses_duo_print(c))

    report.findings = findings
    report.commands_total = commands_total
    report.commands_with_json = commands_with_json
    report.commands_using_print = commands_using_print
    report.commands_with_duo_print = commands_with_duo_print
    report.uses_duo_app = saw_duo_app

    if fix_dry_run:
        from .diff import build_dry_run_diff

        report.diff_preview = build_dry_run_diff(
            project_root=project_root,
            entry=entry,
            commands=all_commands,
        )

    return report


def _find_assignment_lineno(tree: ast.Module, var: str) -> int | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var:
                    return node.lineno
    return None


def _find_assignment_lineno_in_file(path: Path, var: str) -> int | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None
    return _find_assignment_lineno(tree, var)
