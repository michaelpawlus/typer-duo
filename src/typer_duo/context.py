"""Context utilities for detecting output mode and interactivity."""

from __future__ import annotations

import sys
import threading

_local = threading.local()


def _get_json_mode() -> bool:
    return getattr(_local, "json_mode", False)


def _set_json_mode(value: bool) -> None:
    _local.json_mode = value


def is_json_mode() -> bool:
    """Return True if the current command was invoked with --json."""
    return _get_json_mode()


def is_interactive() -> bool:
    """Return True if stdin is a TTY and --json is not set."""
    return sys.stdin.isatty() and not is_json_mode()


def duo_print(message: str) -> None:
    """Print a message to stderr so it never pollutes JSON stdout."""
    print(message, file=sys.stderr)
