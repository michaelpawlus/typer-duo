"""typer-duo: Agent-ready dual-output for Typer CLIs."""

from .app import DuoApp
from .constants import EXIT_ERROR, EXIT_NOT_FOUND, EXIT_OK
from .context import duo_print, is_interactive, is_json_mode
from .decorators import duo_command
from .errors import DuoError

__all__ = [
    "DuoApp",
    "DuoError",
    "EXIT_ERROR",
    "EXIT_NOT_FOUND",
    "EXIT_OK",
    "duo_command",
    "duo_print",
    "is_interactive",
    "is_json_mode",
]
