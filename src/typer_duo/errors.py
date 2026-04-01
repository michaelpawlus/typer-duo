"""Structured error that renders differently based on output mode."""

from __future__ import annotations

import json
import sys
from typing import Any

from .context import is_json_mode


class DuoError(Exception):
    """Structured error with code and optional details.

    In JSON mode: writes structured JSON to stdout.
    In human mode: writes styled error message to stderr.
    Both modes exit with the given code.
    """

    def __init__(
        self,
        message: str,
        code: int = 1,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details

    def render(self) -> None:
        """Render the error to the appropriate output stream and exit."""
        if is_json_mode():
            payload: dict[str, Any] = {"error": self.message, "code": self.code}
            if self.details:
                payload["details"] = self.details
            json.dump(payload, sys.stdout)
            sys.stdout.write("\n")
        else:
            msg = f"Error: {self.message}"
            if self.details:
                detail_parts = [f"  {k}: {v}" for k, v in self.details.items()]
                msg += "\n" + "\n".join(detail_parts)
            print(msg, file=sys.stderr)
        raise SystemExit(self.code)
