"""The @duo_command decorator for individual commands."""

from __future__ import annotations

import functools
import json
import sys
from typing import Any, Callable

from .context import _set_json_mode, duo_print
from .errors import DuoError
from .formatting import format_human


def duo_command(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that adds dual-output behavior to a Typer command.

    The decorated function should return a JSON-serializable value.
    If --json / json_output is set, the return value is serialized to stdout.
    Otherwise, it's auto-formatted for human consumption and written to stderr.

    DuoError exceptions are caught and rendered appropriately for the output mode.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        json_output = kwargs.get("json_output", False)
        _set_json_mode(json_output)

        try:
            result = func(*args, **kwargs)
        except DuoError as e:
            e.render()
            return

        if result is None:
            return

        if json_output:
            json.dump(result, sys.stdout, default=str)
            sys.stdout.write("\n")
        else:
            # Check for a custom format function
            format_fn_name = f"format_{func.__name__}"
            format_fn = func.__globals__.get(format_fn_name)
            if format_fn is not None:
                output = format_fn(result)
            else:
                output = format_human(result)
            if output is not None:
                duo_print(output)

    return wrapper
