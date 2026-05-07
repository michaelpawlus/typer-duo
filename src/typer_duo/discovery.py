"""Project discovery for portfolio-wide audits.

Walks the immediate subdirectories of a root and identifies which ones look
like Python projects with a CLI entry point. Used by ``typer-duo audit-all``.

Discovery rules:

- A directory is a *Python project* if it contains a ``pyproject.toml``.
- A Python project is *CLI-bearing* if its ``pyproject.toml`` declares at
  least one ``[project.scripts]`` entry.
- Directories with no ``pyproject.toml`` are silently skipped.
- Hidden directories (``.git``, ``.venv``, etc.) are skipped.
"""

from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class ProjectPath:
    """A discovered project directory.

    ``has_scripts`` is True iff the project's ``pyproject.toml`` declares a
    non-empty ``[project.scripts]`` table.
    """

    name: str
    path: Path
    has_pyproject: bool
    has_scripts: bool
    scripts: tuple[str, ...] = ()


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _read_scripts(pyproject: Path) -> tuple[bool, tuple[str, ...]]:
    """Return (has_pyproject, scripts) for *pyproject*. Tolerant of malformed files."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return True, ()
    scripts = data.get("project", {}).get("scripts", {}) or {}
    if not isinstance(scripts, dict):
        return True, ()
    names = tuple(sorted(scripts.keys()))
    return True, names


def iter_projects(
    root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Iterator[ProjectPath]:
    """Yield ``ProjectPath`` records for every Python project under *root*.

    Only the immediate children of *root* are considered. Hidden directories
    and anything matching an ``--exclude`` glob are skipped. If ``--include``
    is provided, only directories matching at least one include glob are
    yielded.

    A directory is yielded only if it contains a ``pyproject.toml``. Whether
    it has CLI scripts is reported via the ``has_scripts`` field on the
    returned record so callers can decide what to do with no-CLI projects.
    """
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith("."):
            continue
        if include and not _matches_any(name, include):
            continue
        if exclude and _matches_any(name, exclude):
            continue
        pyproject = entry / "pyproject.toml"
        if not pyproject.is_file():
            continue
        has_py, scripts = _read_scripts(pyproject)
        yield ProjectPath(
            name=name,
            path=entry.resolve(),
            has_pyproject=has_py,
            has_scripts=bool(scripts),
            scripts=scripts,
        )
