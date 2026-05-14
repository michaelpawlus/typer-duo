# typer-duo

Agent-ready dual-output for Typer CLIs: JSON to stdout, human text to stderr.

Stop writing `--json` flag boilerplate. `typer-duo` adds dual-output capability to any [Typer](https://typer.tiangolo.com/) app so every command automatically serves both humans and agents.

## The Problem

Every CLI that supports both human and machine consumers needs the same pattern: check a `--json` flag, route JSON to stdout, format human output to stderr, structure errors consistently, detect TTY for non-interactive mode. It's well-understood but tedious to implement correctly in every command.

## The Solution

```python
from typer_duo import DuoApp

app = DuoApp(name="my-tool")

@app.command()
def status():
    """Show system status."""
    return {"healthy": True, "uptime_seconds": 12345}
```

That's it. Your command now supports both output modes:

```bash
# Human-readable output (stderr)
$ my-tool status
healthy           True
uptime_seconds    12345

# Machine-readable output (stdout)
$ my-tool status --json
{"healthy": true, "uptime_seconds": 12345}
```

## Installation

```bash
pip install typer-duo
```

With optional extras:

```bash
pip install typer-duo[rich]       # Prettier human-readable tables
pip install typer-duo[scaffold]   # Project scaffolding command
pip install typer-duo[all]        # Everything
```

## Quick Start

### Option 1: `DuoApp` (recommended)

Replace `typer.Typer()` with `DuoApp()` and have every command gain `--json` automatically:

```python
from typer_duo import DuoApp

app = DuoApp(name="my-tool")

@app.command()
def users():
    """List all users."""
    return [
        {"name": "Alice", "role": "admin"},
        {"name": "Bob", "role": "user"},
    ]

@app.command()
def greet(name: str):
    """Greet a user."""
    return {"message": f"Hello, {name}!"}

if __name__ == "__main__":
    app()
```

### Option 2: `@duo_command` decorator

Add dual-output to individual commands without changing your Typer app:

```python
import typer
from typer_duo import duo_command

app = typer.Typer()

@app.command()
@duo_command
def status(json_output: bool = typer.Option(False, "--json")):
    """Show system status."""
    return {"healthy": True, "uptime_seconds": 12345}
```

## API Reference

### `DuoApp`

A thin subclass of `typer.Typer`. Every command registered with `@app.command()` automatically gets a `--json` flag. Commands should return a JSON-serializable value instead of printing directly.

**Output routing:**
- `--json`: serializes the return value as JSON to **stdout**
- Without `--json`: auto-formats the return value for humans and writes to **stderr**

### `@duo_command`

Decorator for adding dual-output to a single command on a standard `typer.Typer` app. The decorated function must include a `json_output` parameter wired to `--json`.

### `DuoError`

Structured error that renders differently based on output mode:

```python
from typer_duo import DuoError

@app.command()
def connect():
    raise DuoError(
        "Database connection failed",
        code=1,
        details={"host": "localhost", "port": 5432},
    )
```

```bash
# Human mode
$ my-tool connect
Error: Database connection failed
  host: localhost
  port: 5432

# JSON mode
$ my-tool connect --json
{"error": "Database connection failed", "code": 1, "details": {"host": "localhost", "port": 5432}}
```

Both modes exit with the specified code.

### Context Utilities

```python
from typer_duo import is_json_mode, is_interactive, duo_print

# Check if --json was passed
if is_json_mode():
    ...

# Check if running interactively (TTY + not JSON mode)
if is_interactive():
    confirm = typer.confirm("Are you sure?")
else:
    confirm = True  # Non-interactive: skip prompts

# Print to stderr (never pollutes JSON stdout)
duo_print("Processing...")
```

### Exit Code Constants

```python
from typer_duo import EXIT_OK, EXIT_ERROR, EXIT_NOT_FOUND

# EXIT_OK = 0
# EXIT_ERROR = 1
# EXIT_NOT_FOUND = 2
```

### Human Formatting

Return values are auto-formatted for human output based on their type:

| Return type    | Human output              |
|----------------|---------------------------|
| `dict`         | Key-value table           |
| `list[dict]`   | Table with column headers |
| `str`          | Printed as-is             |
| `list[str]`    | One item per line         |
| `None`         | No output                 |

Install `rich` for prettier tables: `pip install typer-duo[rich]`

#### Custom Formatting

Override auto-formatting by defining a `format_<command_name>` function alongside your command:

```python
@app.command()
def status():
    return {"healthy": True, "uptime": 12345}

def format_status(result: dict) -> str:
    icon = "OK" if result["healthy"] else "FAIL"
    return f"[{icon}] Uptime: {result['uptime']}s"
```

Or implement `__duo_format__()` on a return object:

```python
class StatusResult:
    def __init__(self, healthy: bool, uptime: int):
        self.healthy = healthy
        self.uptime = uptime

    def __duo_format__(self) -> str:
        icon = "OK" if self.healthy else "FAIL"
        return f"[{icon}] Uptime: {self.uptime}s"
```

## Project Scaffolding

Generate a new CLI project pre-wired with typer-duo:

```bash
pip install typer-duo[scaffold]
typer-duo my-tool --description "My awesome CLI"
```

This creates:

```
my-tool/
  pyproject.toml          # With typer-duo dependency and entry point
  src/my_tool/__init__.py
  src/my_tool/cli.py      # Example DuoApp with one command
  tests/test_cli.py       # Example tests
  CLAUDE.md               # Documents CLI commands for agent use
```

Options:

```
typer-duo PROJECT_NAME [OPTIONS]

Options:
  --description TEXT   One-line project description
  --author TEXT        Author name for pyproject.toml
  --no-tests           Skip test skeleton
  -o, --output-dir DIR Parent directory (default: current dir)
```

## Migrating an Existing Typer App

```python
# Before: manual --json boilerplate in every command
@app.command()
def status(json_output: bool = typer.Option(False, "--json")):
    result = get_status()
    if json_output:
        import json, sys
        json.dump(result, sys.stdout)
    else:
        print(format_status(result), file=sys.stderr)

# After: return the data, let typer-duo handle the rest
from typer_duo import DuoApp

app = DuoApp()

@app.command()
def status():
    return get_status()
```

## Closing the Audit Loop: `audit` + `fix`

`typer-duo audit` tells you *what* in a project isn't agent-ready. `typer-duo
fix` applies the standard remediation for each finding.

```bash
# 1. See what's wrong.
typer-duo audit path/to/repo --json

# 2. Preview the patches before writing.
typer-duo fix path/to/repo --dry-run

# 3. Apply the safe fixers.
typer-duo fix path/to/repo

# 4. JSON report for agents/CI.
typer-duo fix path/to/repo --dry-run --json
```

Output (`--json`):

```json
{
  "dry_run": true,
  "applied": [{"fixer_id": "add-json-flag", "diff": "...", "edits": [...]}],
  "skipped": [{"fixer_id": "add-project-script-entry", "status": "no-op", ...}],
  "errors": []
}
```

### Available fixers

| Fixer ID | Addresses | Default? | What it does |
| --- | --- | --- | --- |
| `add-json-flag` | `missing-json-flag` | yes | Adds `json_output: JsonFlag = False` to every command lacking `--json` and inserts the `from typer_duo import …` line. |
| `replace-print-with-stderr` | `bare-print-stdout` | yes | Rewrites bare `print(...)` calls inside command bodies to `print(..., file=sys.stderr)` (and inserts `import sys` if needed). |
| `add-project-script-entry` | – | yes | Adds a `[project.scripts]` entry in `pyproject.toml` pointing at the detected Typer/DuoApp module. No-op when one already exists. |
| `migrate-to-duoapp` | `app-uses-plain-typer` | **opt-in** | Rewrites `app = typer.Typer(...)` to `app = DuoApp(...)`. Gated behind `--check migrate-to-duoapp` because it changes the runtime behaviour of every command in the entry point. |

### Properties

* **Idempotent.** A second `fix` run produces zero new changes.
* **Drift-free vs. audit.** Both `audit --fix-dry-run` and `fix` reuse the
  same AST utilities, so a finding and its fix never disagree.
* **Pure-AST proposals.** Each fixer reads the source on disk, never imports
  or executes the target.

### Exit codes

* `0` — fix ran successfully (including the no-op case).
* `1` — unknown `--check` ID, a fixer raised, or a write failed.
* `2` — no Typer entry point detected at the target path.

## Design Principles

1. **Zero magic.** Explicit decorators, not monkey-patching.
2. **Minimal surface.** The smallest useful API.
3. **Typer-native.** Extends Typer's conventions, doesn't fight them.
4. **Agent-friendly by default.** JSON to stdout, human text to stderr, structured errors, meaningful exit codes.

## Adopters

CLIs in the wild that use typer-duo. Open a PR to add yours.

- **[agent-cron](https://github.com/michaelpawlus/agent-cron)** — Scheduled headless Claude Code workflows. First reference adopter; canonical example of a multi-command `DuoApp` migration from plain Typer.

## Development

```bash
git clone https://github.com/michaelpawlus/typer-duo.git
cd typer-duo
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## License

MIT
