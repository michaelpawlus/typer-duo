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


def _make_duo_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap *func* with dual-output behavior (--json flag, error handling, formatting).

    Returns a new function with the original params plus a ``json_output`` keyword
    that Typer exposes as ``--json``.
    """
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

    return wrapper


def _patch_typer_with_duo(typer_instance: typer.Typer) -> None:
    """Monkey-patch a plain Typer so its commands get duo wrapping.

    Handles three cases:
    1. Commands already registered on *typer_instance* (retroactive wrap).
    2. Commands registered in the future via ``@typer_instance.command()`` (patched method).
    3. Nested sub-apps already attached or added later (recursive patch).
    """
    # 1. Retroactively wrap already-registered commands
    for cmd_info in typer_instance.registered_commands:
        if cmd_info.callback is not None:
            cmd_info.callback = _make_duo_wrapper(cmd_info.callback)

    # 2. Patch .command() for future registrations
    original_command = typer_instance.command

    def patched_command(*args: Any, duo: bool = True, **kwargs: Any):
        decorator = original_command(*args, **kwargs)
        if not duo:
            return decorator

        def duo_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return decorator(_make_duo_wrapper(func))

        return duo_decorator

    typer_instance.command = patched_command

    # 3. Recursively patch nested sub-apps already registered
    for group_info in typer_instance.registered_groups:
        if group_info.typer_instance and not isinstance(
            group_info.typer_instance, DuoApp
        ):
            _patch_typer_with_duo(group_info.typer_instance)

    # 4. Patch .add_typer() so future nested sub-apps also get wrapped
    original_add_typer = typer_instance.add_typer

    def patched_add_typer(
        child: typer.Typer, *args: Any, duo: bool = True, **kwargs: Any
    ) -> None:
        if duo and not isinstance(child, DuoApp):
            _patch_typer_with_duo(child)
        original_add_typer(child, *args, **kwargs)

    typer_instance.add_typer = patched_add_typer


class DuoApp(typer.Typer):
    """A thin subclass of typer.Typer that adds a global --json flag to every command.

    Commands should return JSON-serializable values. The return value is:
    - Serialized to stdout as JSON when --json is set
    - Auto-formatted for human consumption and written to stderr otherwise
    """

    def command(
        self,
        *args: Any,
        duo: bool = True,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Override command registration to wrap functions with dual-output behavior.

        Pass ``duo=False`` to skip the dual-output wrapping for this command.
        """
        decorator = super().command(*args, **kwargs)
        if not duo:
            return decorator

        def duo_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return decorator(_make_duo_wrapper(func))

        return duo_decorator

    def add_typer(
        self,
        typer_instance: typer.Typer,
        *args: Any,
        duo: bool = True,
        **kwargs: Any,
    ) -> None:
        """Override add_typer to auto-wrap child commands with dual-output.

        When *duo* is True (the default) and the child is a plain ``typer.Typer``
        (not already a ``DuoApp``), its commands are monkey-patched so they get
        the ``--json`` flag and dual-output wrapping automatically.

        Pass ``duo=False`` to skip wrapping for this sub-app entirely.
        """
        if duo and not isinstance(typer_instance, DuoApp):
            _patch_typer_with_duo(typer_instance)
        super().add_typer(typer_instance, *args, **kwargs)
