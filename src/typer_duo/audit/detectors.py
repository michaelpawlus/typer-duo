"""Per-command and top-level detectors.

Each detector takes structured AST context and returns a list of Findings.
The detectors do not execute the target code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .models import Finding

JSON_PARAM_NAMES = {"json_output", "json_", "json"}
JSON_FLAG_TYPE_NAMES = {"JsonFlag"}


@dataclass
class CommandInfo:
    """A discovered Typer command function with the metadata detectors need."""

    name: str
    func_node: ast.FunctionDef | ast.AsyncFunctionDef
    file: str
    relative_file: str  # path relative to project root, for reports
    decorator_app_var: str  # the "app" in "@app.command(...)"
    is_on_duo_app: bool


def _arg_has_json_param(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the function's signature exposes a JSON-style flag."""
    all_args = list(func.args.args) + list(func.args.kwonlyargs)
    for arg in all_args:
        if arg.arg in JSON_PARAM_NAMES:
            return True
        # Type-annotated as JsonFlag (or JsonFlag = ...)?
        if arg.annotation is not None:
            ann_name = _annotation_name(arg.annotation)
            if ann_name in JSON_FLAG_TYPE_NAMES:
                return True
    return False


def _annotation_name(node: ast.expr) -> str | None:
    """Pull a leaf name out of an annotation node (handles Foo, mod.Foo, Foo[...])."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _annotation_name(node.value)
    return None


def _iter_calls(func: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(func) if isinstance(n, ast.Call)]


def _call_name(call: ast.Call) -> str | None:
    """Return the function name being called: ``foo`` for ``foo()``, ``bar`` for ``x.bar()``."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _print_writes_to_stderr(call: ast.Call) -> bool:
    """True if a ``print(...)`` call has ``file=sys.stderr`` (or any stderr-like target)."""
    for kw in call.keywords:
        if kw.arg == "file":
            target = kw.value
            # sys.stderr or just stderr
            if isinstance(target, ast.Attribute) and target.attr == "stderr":
                return True
            if isinstance(target, ast.Name) and target.id == "stderr":
                return True
    return False


def _is_module_attr_call(call: ast.Call, module: str, attr: str) -> bool:
    """True if call looks like ``module.attr(...)``."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == attr:
        if isinstance(func.value, ast.Name) and func.value.id == module:
            return True
    return False


def detect_missing_json_flag(cmd: CommandInfo) -> list[Finding]:
    """Error: the command has no recognized JSON parameter and is not on a DuoApp."""
    if cmd.is_on_duo_app:
        return []
    if _arg_has_json_param(cmd.func_node):
        return []
    return [
        Finding(
            id="missing-json-flag",
            severity="error",
            detail=(
                f"Command '{cmd.name}' has no `--json` parameter; add "
                f"`json_output: JsonFlag = False` or migrate to `DuoApp`."
            ),
            file=cmd.relative_file,
            line=cmd.func_node.lineno,
            command=cmd.name,
        )
    ]


def detect_bare_print_stdout(cmd: CommandInfo) -> list[Finding]:
    """Warning: bare ``print(...)`` calls writing to stdout from a command body."""
    findings: list[Finding] = []
    for call in _iter_calls(cmd.func_node):
        if not isinstance(call.func, ast.Name) or call.func.id != "print":
            continue
        if _print_writes_to_stderr(call):
            continue
        # Render a short snippet of the print call for context.
        snippet = _short_call_repr(call)
        findings.append(
            Finding(
                id="bare-print-stdout",
                severity="warning",
                detail=(
                    f"`{snippet}` writes human text to stdout; use "
                    f"`duo_print(...)` or pass `file=sys.stderr`."
                ),
                file=cmd.relative_file,
                line=call.lineno,
                command=cmd.name,
            )
        )
    return findings


def detect_stderr_on_json_path(cmd: CommandInfo) -> list[Finding]:
    """Info: ``Console()`` instantiated without ``stderr=True`` inside a command."""
    findings: list[Finding] = []
    for call in _iter_calls(cmd.func_node):
        # Match Console(...) or rich.console.Console(...).
        name = _call_name(call)
        if name != "Console":
            continue
        has_stderr = any(
            kw.arg == "stderr" and isinstance(kw.value, ast.Constant) and kw.value.value
            for kw in call.keywords
        )
        if has_stderr:
            continue
        findings.append(
            Finding(
                id="stderr-on-json-path",
                severity="info",
                detail=(
                    "`Console()` defaults to stdout; pass `stderr=True` or it "
                    "will pollute JSON output when --json is set."
                ),
                file=cmd.relative_file,
                line=call.lineno,
                command=cmd.name,
            )
        )
    return findings


def detect_mixed_output_style(cmd: CommandInfo) -> list[Finding]:
    """Info: command mixes plain ``print()`` with ``console.print()``."""
    has_print = False
    has_console_print = False
    for call in _iter_calls(cmd.func_node):
        if isinstance(call.func, ast.Name) and call.func.id == "print":
            has_print = True
        elif (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "print"
            and isinstance(call.func.value, ast.Name)
        ):
            # ``console.print(...)`` or any ``<name>.print(...)`` other than ``print``
            has_console_print = True
    if has_print and has_console_print:
        return [
            Finding(
                id="mixed-output-style",
                severity="info",
                detail=(
                    f"Command '{cmd.name}' mixes `print()` and `<console>.print()`; "
                    f"pick one for consistency."
                ),
                file=cmd.relative_file,
                line=cmd.func_node.lineno,
                command=cmd.name,
            )
        ]
    return []


def _short_call_repr(call: ast.Call) -> str:
    """Approximate source for a function call (for findings detail messages)."""
    try:
        return ast.unparse(call)[:80]
    except Exception:  # pragma: no cover - very old python paths
        return "print(...)"


def run_per_command_detectors(cmd: CommandInfo) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(detect_missing_json_flag(cmd))
    findings.extend(detect_bare_print_stdout(cmd))
    findings.extend(detect_stderr_on_json_path(cmd))
    findings.extend(detect_mixed_output_style(cmd))
    return findings


def detect_app_uses_plain_typer(
    framework: str, file: str, line: int
) -> list[Finding]:
    if framework == "typer":
        return [
            Finding(
                id="app-uses-plain-typer",
                severity="warning",
                detail=(
                    "Entry point uses `typer.Typer(...)`; migrate to "
                    "`DuoApp(...)` so every command gets `--json` automatically."
                ),
                file=file,
                line=line,
                command=None,
            )
        ]
    return []


def detect_no_stderr_console(
    tree: ast.Module, file: str
) -> list[Finding]:
    """Info: module has no ``Console(stderr=True)`` instance at module level."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _call_name(node) == "Console":
                for kw in node.keywords:
                    if (
                        kw.arg == "stderr"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value
                    ):
                        return []
    return [
        Finding(
            id="no-stderr-console",
            severity="info",
            detail=(
                "Module has no `Console(stderr=True)` instance; commands using "
                "rich for human output should write to stderr."
            ),
            file=file,
            line=1,
            command=None,
        )
    ]
