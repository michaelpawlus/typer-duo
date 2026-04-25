# typer-duo

Agent-ready dual-output library for Typer CLIs: JSON to stdout, human text to stderr.

## Project Structure

- `src/typer_duo/` — library source (src layout)
- `tests/` — pytest test suite
- Build system: setuptools via pyproject.toml

## CLI Commands

```
typer-duo init PROJECT_NAME [--description TEXT] [--author TEXT] [--no-tests] [-o DIR]
typer-duo audit PATH [--json] [--strict] [--fix-dry-run] [--include GLOB]... [--exclude GLOB]...
```

- `init` — scaffolds new projects pre-wired with dual-output patterns.
- `audit` — points at an existing Typer-based project and reports which commands
  are not agent-ready (missing `--json`, bare `print()` to stdout, plain
  `typer.Typer` instead of `DuoApp`, etc.). Pure static analysis on the AST —
  it never imports or executes the target. Safe to run against any repo.

### `audit` exit codes
- `0` — audit ran successfully (regardless of findings).
- `1` — audit itself errored, OR `--strict` was set and a finding has severity
  `error`.
- `2` — no Typer entry point detected at the target path.

### `audit` pairing with `conductor doctor`
`conductor doctor --check-subcommands` flags repos that fail the agent-compat
check. `typer-duo audit PATH` says exactly what to change in each one.

## Public API

- `DuoApp` — Typer subclass that adds `--json` to every command
  - `DuoApp.add_typer(child, ..., duo=True)` — mounts a sub-app; plain `typer.Typer` children are auto-wrapped with `--json` support. Pass `duo=False` to skip wrapping.
  - `DuoApp.command(..., duo=True)` — registers a command; pass `duo=False` to skip dual-output wrapping for that command.
  - Sub-apps that are themselves `DuoApp` instances work natively (no patching needed).
  - Nested sub-apps (grandchild apps) are recursively wrapped.
- `@duo_command` — decorator for individual commands on a standard Typer app
- `JsonFlag` — `Annotated[bool, typer.Option("--json")]` alias for hand-written commands
- `DuoError` — structured error (renders as JSON or human text)
- `is_json_mode()`, `is_interactive()`, `duo_print()` — context utilities
- `EXIT_OK`, `EXIT_ERROR`, `EXIT_NOT_FOUND` — exit code constants
- `typer_duo.audit.audit_project(path, ...)` — programmatic API for the audit

## Running Tests

```bash
.venv/bin/pytest
```

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
