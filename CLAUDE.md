# typer-duo

Agent-ready dual-output library for Typer CLIs: JSON to stdout, human text to stderr.

## Project Structure

- `src/typer_duo/` — library source (src layout)
- `tests/` — pytest test suite
- Build system: setuptools via pyproject.toml

## CLI Commands

```
typer-duo init PROJECT_NAME [--description TEXT] [--author TEXT] [--no-tests] [-o DIR]
```

The `typer-duo` CLI scaffolds new projects pre-wired with dual-output patterns.

## Public API

- `DuoApp` — Typer subclass that adds `--json` to every command
- `@duo_command` — decorator for individual commands on a standard Typer app
- `DuoError` — structured error (renders as JSON or human text)
- `is_json_mode()`, `is_interactive()`, `duo_print()` — context utilities
- `EXIT_OK`, `EXIT_ERROR`, `EXIT_NOT_FOUND` — exit code constants

## Running Tests

```bash
.venv/bin/pytest
```

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
