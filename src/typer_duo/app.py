"""DuoApp — a Typer subclass with automatic dual-output support."""

from __future__ import annotations

import inspect
import json
import sys
from typing import Any, Callable

import typer

from .context import _set_json_mode, duo_print
from .errors import DuoError
from .formatting import format_human


class DuoApp(typer.Typer):
    """A thin subclass of typer.Typer that adds a global --json flag to every command.

    Commands should return JSON-serializable values. The return value is:
    - Serialized to stdout as JSON when --json is set
    - Auto-formatted for human consumption and written to stderr otherwise
    """

    def command(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Override command registration to wrap functions with dual-output behavior."""
        decorator = super().command(*args, **kwargs)

        def duo_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Capture the original function's globals for format_ lookup
            func_globals = func.__globals__

            def wrapper(
                *func_args: Any,
                json_output: bool = typer.Option(
                    False, "--json", help="Output as JSON to stdout"
                ),
                **func_kwargs: Any,
            ) -> None:
                _set_json_mode(json_output)

                try:
                    result = func(*func_args, **func_kwargs)
                except DuoError as e:
                    e.render()
                    return

                if result is None:
                    return

                if json_output:
                    json.dump(result, sys.stdout, default=str)
                    sys.stdout.write("\n")
                else:
                    format_fn_name = f"format_{func.__name__}"
                    format_fn = func_globals.get(format_fn_name)
                    if format_fn is not None:
                        output = format_fn(result)
                    else:
                        output = format_human(result)
                    if output is not None:
                        duo_print(output)

            # Build a proper signature so Typer sees both the original
            # function's params AND the added json_output param.
            orig_sig = inspect.signature(func)
            json_param = inspect.Parameter(
                "json_output",
                inspect.Parameter.KEYWORD_ONLY,
                default=typer.Option(False, "--json", help="Output as JSON to stdout"),
            )
            new_params = list(orig_sig.parameters.values()) + [json_param]
            wrapper.__signature__ = orig_sig.replace(parameters=new_params)
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            wrapper.__module__ = func.__module__

            return decorator(wrapper)

        return duo_decorator
