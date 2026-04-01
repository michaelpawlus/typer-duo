"""Human output formatting for command return values."""

from __future__ import annotations

from typing import Any


def _format_dict_plain(data: dict[str, Any]) -> str:
    """Format a dict as a key-value table."""
    if not data:
        return ""
    max_key_len = max(len(str(k)) for k in data)
    lines = []
    for key, value in data.items():
        lines.append(f"{str(key).ljust(max_key_len)}  {value}")
    return "\n".join(lines)


def _format_list_of_dicts_plain(data: list[dict[str, Any]]) -> str:
    """Format a list of dicts as a table with column headers."""
    if not data:
        return ""
    columns = list(data[0].keys())
    col_widths = {col: len(str(col)) for col in columns}
    for row in data:
        for col in columns:
            val = str(row.get(col, ""))
            col_widths[col] = max(col_widths[col], len(val))

    header = "  ".join(str(col).ljust(col_widths[col]) for col in columns)
    separator = "  ".join("-" * col_widths[col] for col in columns)
    rows = []
    for row in data:
        row_str = "  ".join(
            str(row.get(col, "")).ljust(col_widths[col]) for col in columns
        )
        rows.append(row_str)
    return "\n".join([header, separator, *rows])


def _try_rich_dict(data: dict[str, Any]) -> str | None:
    """Try to format a dict using rich, return None if not available."""
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        return None

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(str(key), str(value))

    console = Console(file=None, force_terminal=False)
    with console.capture() as capture:
        console.print(table)
    return capture.get().rstrip()


def _try_rich_list_of_dicts(data: list[dict[str, Any]]) -> str | None:
    """Try to format a list of dicts using rich, return None if not available."""
    if not data:
        return None
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        return None

    columns = list(data[0].keys())
    table = Table(box=None)
    for col in columns:
        table.add_column(str(col), style="bold" if col == columns[0] else "")
    for row in data:
        table.add_row(*(str(row.get(col, "")) for col in columns))

    console = Console(file=None, force_terminal=False)
    with console.capture() as capture:
        console.print(table)
    return capture.get().rstrip()


def format_human(result: Any) -> str | None:
    """Format a command's return value for human-readable output.

    Returns None if the result is None (no output).
    """
    if result is None:
        return None

    if isinstance(result, str):
        return result

    if isinstance(result, list):
        if not result:
            return ""
        if all(isinstance(item, dict) for item in result):
            rich_out = _try_rich_list_of_dicts(result)
            return rich_out if rich_out is not None else _format_list_of_dicts_plain(result)
        return "\n".join(str(item) for item in result)

    if isinstance(result, dict):
        rich_out = _try_rich_dict(result)
        return rich_out if rich_out is not None else _format_dict_plain(result)

    # For objects with __duo_format__, use that
    if hasattr(result, "__duo_format__"):
        return result.__duo_format__()

    return str(result)
