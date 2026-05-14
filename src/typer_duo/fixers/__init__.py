"""Fix templates that close the ``audit`` loop.

Each fixer is a pure function taking the project root and an
:class:`~typer_duo.audit.AuditReport`, returning a :class:`FixResult`
describing the edits it would make. The ``typer-duo fix`` CLI runs them
either in dry-run mode (printing diffs) or applies the edits to disk.
"""

from __future__ import annotations

from typing import Callable

from .add_json_flag import propose as _propose_add_json_flag
from .add_project_script_entry import propose as _propose_add_project_script_entry
from .migrate_to_duoapp import propose as _propose_migrate_to_duoapp
from .models import FixEdit, FixResult, FixerProposeFn
from .replace_print_with_stderr import propose as _propose_replace_print_with_stderr

# Map fixer IDs (stable, public) -> propose function.
# A fixer is "safe-by-default" if it appears in DEFAULT_FIXERS. The
# ``migrate-to-duoapp`` fixer is opt-in only (must be passed via --check).
FIXERS: dict[str, FixerProposeFn] = {
    "add-json-flag": _propose_add_json_flag,
    "replace-print-with-stderr": _propose_replace_print_with_stderr,
    "add-project-script-entry": _propose_add_project_script_entry,
    "migrate-to-duoapp": _propose_migrate_to_duoapp,
}

DEFAULT_FIXERS: tuple[str, ...] = (
    "add-json-flag",
    "replace-print-with-stderr",
    "add-project-script-entry",
)

OPT_IN_FIXERS: tuple[str, ...] = ("migrate-to-duoapp",)


def get(fixer_id: str) -> Callable | None:
    """Return the propose function for *fixer_id* or None if unknown."""
    return FIXERS.get(fixer_id)


__all__ = [
    "FIXERS",
    "DEFAULT_FIXERS",
    "OPT_IN_FIXERS",
    "FixEdit",
    "FixResult",
    "FixerProposeFn",
    "get",
]
