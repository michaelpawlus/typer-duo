"""Data models shared by every fixer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from ..audit.models import AuditReport

# A fixer is a pure function: (project_root, audit_report) -> FixResult.
FixerProposeFn = Callable[[Path, AuditReport], "FixResult"]

FixStatus = Literal["proposed", "applied", "no-op", "skipped", "error"]


@dataclass
class FixEdit:
    """A single file edit a fixer wants to make.

    The fixer never writes to disk; the CLI applies the edit when not in
    dry-run mode. ``path`` is relative to the project root.
    """

    path: str
    original: str
    updated: str
    is_new: bool = False

    @property
    def is_noop(self) -> bool:
        return not self.is_new and self.original == self.updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "is_new": self.is_new,
            "is_noop": self.is_noop,
        }


@dataclass
class FixResult:
    """Outcome of running one fixer against one project."""

    fixer_id: str
    status: FixStatus
    edits: list[FixEdit] = field(default_factory=list)
    reason: str | None = None
    findings_addressed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(not e.is_noop for e in self.edits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixer_id": self.fixer_id,
            "status": self.status,
            "reason": self.reason,
            "findings_addressed": list(self.findings_addressed),
            "edits": [e.to_dict() for e in self.edits],
        }
