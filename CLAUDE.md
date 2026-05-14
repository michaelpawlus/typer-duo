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
typer-duo audit-all [--root PATH] [--json] [--include GLOB]... [--exclude GLOB]...
                    [--since FILE] [--output PATH] [--fail-under FLOAT]
                    [--skip-no-cli] [--workers N]
typer-duo fix PATH [--check ID]... [--dry-run] [--json]
```

- `init` — scaffolds new projects pre-wired with dual-output patterns.
- `audit` — points at an existing Typer-based project and reports which commands
  are not agent-ready (missing `--json`, bare `print()` to stdout, plain
  `typer.Typer` instead of `DuoApp`, etc.). Pure static analysis on the AST —
  it never imports or executes the target. Safe to run against any repo.
- `audit-all` — depth-first audit across every project under `--root` (default
  `~/projects`), aggregated into a single JSON scorecard. Reuses the same
  AST audit per project (no subprocess), parallelized with a thread pool.
  Pair with `--since FILE` to diff against a previous scorecard so the
  artifact becomes diffable over time.
- `fix` — closes the audit loop. Applies the standard remediation for each
  agent-readiness finding `audit` surfaces (add `--json`, redirect bare
  `print()` to stderr, add a `[project.scripts]` entry, optionally migrate
  `typer.Typer` → `DuoApp`). Pure AST/text patches; never imports or runs
  the target. Idempotent. See "Fix subcommand" below.

### `audit` exit codes
- `0` — audit ran successfully (regardless of findings).
- `1` — audit itself errored, OR `--strict` was set and a finding has severity
  `error`.
- `2` — no Typer entry point detected at the target path.

### `audit-all` exit codes
- `0` — scorecard generated successfully.
- `1` — `--fail-under` threshold not met, or `--since` file unreadable.

### `audit-all` discovery rules
A directory under `--root` is included iff it contains a `pyproject.toml`.
Hidden directories (`.git`, `.venv`, …) are skipped. Projects with no
`[project.scripts]` table are reported as `status: "no-cli"` unless
`--skip-no-cli` is passed.

### `audit-all` scorecard schema (v1)
```json
{
  "schema_version": 1,
  "generated_at": "<ISO-8601 UTC>",
  "root": "<root path>",
  "portfolio_score": 0.0,
  "projects": [
    {
      "name": "...",
      "path": "...",
      "status": "ok | warn | fail | no-cli | non-typer",
      "score": 0.0,
      "checks": {
        "json_flag_parity": "pass | warn | fail",
        "error_shape": "pass | warn | fail",
        "duo_registered": "pass | warn | fail",
        "exit_codes": "pass | warn | fail"
      },
      "commands_audited": 0,
      "commands_failing": []
    }
  ],
  "summary": {
    "total_projects": 0, "with_cli": 0, "passing": 0,
    "warning": 0, "failing": 0, "no_cli": 0
  },
  "diff": {
    "vs_baseline": "<ISO-8601 UTC>",
    "improved": [], "regressed": [], "newly_added": [], "removed": []
  }
}
```
`diff` is only present when `--since FILE` is supplied. `score` is `null`
for `no-cli` and `non-typer` entries; those are excluded from
`portfolio_score` (a simple mean of scorable projects).

### `fix` subcommand

Closes the loop on `audit`. Each fixer maps to an audit finding:

| Fixer ID | Default? | Addresses |
| --- | --- | --- |
| `add-json-flag` | yes | `missing-json-flag` |
| `replace-print-with-stderr` | yes | `bare-print-stdout` |
| `add-project-script-entry` | yes | (no finding -- triggered by detected Typer module + no `[project.scripts]`) |
| `migrate-to-duoapp` | **opt-in** | `app-uses-plain-typer` |

`migrate-to-duoapp` only runs when passed via `--check migrate-to-duoapp`
because it changes every command's runtime behaviour.

#### `fix` exit codes

- `0` — fix ran successfully (including all-no-op).
- `1` — unknown `--check` ID, a fixer raised, or a file write failed.
- `2` — no Typer entry point detected at the target path.

#### `fix --json` payload

```json
{
  "dry_run": false,
  "applied": [
    {
      "fixer_id": "add-json-flag",
      "status": "applied",
      "edits": [{"path": "src/x/cli.py", "is_new": false, "is_noop": false}],
      "findings_addressed": ["missing-json-flag"]
    }
  ],
  "skipped": [
    {"fixer_id": "add-project-script-entry", "status": "no-op",
     "reason": "[project.scripts] already maps to x.cli:app"}
  ],
  "errors": []
}
```

In `--dry-run --json` mode each `applied` entry also carries a `diff` field
with the unified diff that would be written. `audit --fix-dry-run` and
`fix` share the same AST utilities, so the two never produce conflicting
patches on the same input.

### `audit` / `audit-all` pairing with `conductor doctor`
`conductor doctor --check-subcommands` flags repos that fail the agent-compat
check. `typer-duo audit PATH` says exactly what to change in each one.
`typer-duo audit-all --json` produces the portfolio-wide scorecard that
`conductor doctor --report` and `code-daily portfolio sweep` can both ingest.

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
- `typer_duo.audit.audit_project(path, ...)` — programmatic API for the per-project audit
- `typer_duo.discovery.iter_projects(root, ...)` — yields `ProjectPath` records for portfolio walks
- `typer_duo.scorecard.{Scorecard, ProjectScore, build_scorecard, score_from_report, compute_diff}` — programmatic API for the portfolio scorecard
- `typer_duo.fixers.{FIXERS, DEFAULT_FIXERS, OPT_IN_FIXERS, FixResult, FixEdit, get}` — programmatic API for the `fix` subcommand (each fixer module exposes `propose(project_root, audit_report) -> FixResult`)

## Running Tests

```bash
.venv/bin/pytest
```

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
