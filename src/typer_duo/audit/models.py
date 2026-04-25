"""Data models for the audit subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    """A single issue surfaced by an audit detector."""

    id: str
    severity: Severity
    detail: str
    file: str
    line: int
    command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "command": self.command,
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "id": self.id,
            "detail": self.detail,
        }
        return out


@dataclass
class EntryPoint:
    """Detected CLI entry point for a target project."""

    script_name: str | None
    module: str | None
    app_var: str | None
    framework: str  # "typer" | "duo" | "unknown"
    file: str | None = None  # absolute path to the module's source file

    def to_dict(self) -> dict[str, Any]:
        return {
            "script_name": self.script_name,
            "module": self.module,
            "app_var": self.app_var,
            "framework": self.framework,
        }


@dataclass
class AuditReport:
    """Top-level audit result."""

    audited_at: str
    path: str
    entry_point: EntryPoint
    findings: list[Finding] = field(default_factory=list)
    diff_preview: str | None = None
    commands_total: int = 0
    commands_with_json: int = 0
    commands_using_print: int = 0
    commands_with_duo_print: int = 0
    uses_duo_app: bool = False

    @property
    def severity_max(self) -> Severity | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity

    @property
    def score(self) -> int:
        """Percent of commands that are agent-compat-clean (no error or warning).

        A command is "clean" if it has --json (or app uses DuoApp) and does not
        emit bare prints to stdout.
        """
        if self.commands_total == 0:
            return 100
        # Commands that are clean = commands_with_json (or DuoApp-managed) minus those using print
        # For DuoApp we treat all commands as having --json by construction.
        json_covered = (
            self.commands_total if self.uses_duo_app else self.commands_with_json
        )
        clean = max(0, json_covered - self.commands_using_print)
        return int(round(100 * clean / self.commands_total))

    def to_dict(self) -> dict[str, Any]:
        sev_max = self.severity_max
        return {
            "audited_at": self.audited_at,
            "path": self.path,
            "entry_point": self.entry_point.to_dict(),
            "summary": {
                "commands_total": self.commands_total,
                "commands_with_json": self.commands_with_json,
                "commands_using_print": self.commands_using_print,
                "commands_with_duo_print": self.commands_with_duo_print,
                "score": self.score,
                "severity_max": sev_max,
            },
            "findings": [f.to_dict() for f in self.findings],
            "diff_preview": self.diff_preview,
        }


def severity_rank(sev: Severity) -> int:
    return _SEVERITY_RANK[sev]
