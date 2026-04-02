"""Tests for sub-app / add_typer support in DuoApp."""

import json

import typer
from typer.testing import CliRunner

from typer_duo import DuoApp, DuoError

runner = CliRunner()


# ---------------------------------------------------------------------------
# 5.1 — DuoApp child on DuoApp parent (Option A)
# ---------------------------------------------------------------------------


def test_duoapp_child_json_mode():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("ping")
    def ping():
        return {"pong": True}

    result = runner.invoke(app, ["child", "ping", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"pong": True}


def test_duoapp_child_human_mode():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("ping")
    def ping():
        return {"pong": True}

    result = runner.invoke(app, ["child", "ping"])
    assert result.exit_code == 0
    assert "pong" in result.output


def test_duoapp_child_with_arguments():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("greet")
    def greet(name: str):
        return {"message": f"Hello, {name}!"}

    result = runner.invoke(app, ["child", "greet", "Alice", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["message"] == "Hello, Alice!"


def test_duoapp_child_duo_error():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("fail")
    def fail():
        raise DuoError("broken", code=2)

    result = runner.invoke(app, ["child", "fail", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "broken"
    assert payload["code"] == 2


def test_duoapp_child_returns_none():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("noop")
    def noop():
        return None

    result = runner.invoke(app, ["child", "noop"])
    assert result.exit_code == 0


def test_duoapp_child_returns_list():
    app = DuoApp(name="root")
    child = DuoApp(help="Child commands")
    app.add_typer(child, name="child")

    @child.command("users")
    def users():
        return [{"name": "Alice"}, {"name": "Bob"}]

    result = runner.invoke(app, ["child", "users", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload) == 2
    assert payload[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# 5.2 — Plain Typer child auto-wrapped (Option B)
# ---------------------------------------------------------------------------


def test_plain_typer_child_auto_wrapped_json():
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")
    app.add_typer(child, name="child")

    @child.command("ping")
    def ping():
        return {"pong": True}

    result = runner.invoke(app, ["child", "ping", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"pong": True}


def test_plain_typer_child_auto_wrapped_human():
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")
    app.add_typer(child, name="child")

    @child.command("ping")
    def ping():
        return {"pong": True}

    result = runner.invoke(app, ["child", "ping"])
    assert result.exit_code == 0
    assert "pong" in result.output


def test_plain_typer_child_command_before_add():
    """Commands registered BEFORE add_typer() should also get --json."""
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")

    @child.command("early")
    def early():
        return {"registered": "before add_typer"}

    app.add_typer(child, name="child")

    result = runner.invoke(app, ["child", "early", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["registered"] == "before add_typer"


def test_plain_typer_child_command_after_add():
    """Commands registered AFTER add_typer() should also get --json."""
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")
    app.add_typer(child, name="child")

    @child.command("late")
    def late():
        return {"registered": "after add_typer"}

    result = runner.invoke(app, ["child", "late", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["registered"] == "after add_typer"


def test_plain_typer_child_duo_error():
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")
    app.add_typer(child, name="child")

    @child.command("fail")
    def fail():
        raise DuoError("broke", code=3, details={"hint": "check logs"})

    result = runner.invoke(app, ["child", "fail", "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.output)
    assert payload["error"] == "broke"
    assert payload["details"]["hint"] == "check logs"


def test_plain_typer_child_custom_format_fn():
    """format_{name} lookup should work for wrapped child commands."""
    app = DuoApp(name="root")
    child = typer.Typer(help="Plain child")
    app.add_typer(child, name="child")

    # Inject format function into module globals BEFORE defining the command,
    # because _make_duo_wrapper captures func.__globals__ at decoration time.
    def _fmt(data):
        return "\n".join(f"- {d['name']}" for d in data)

    globals()["format_items"] = _fmt

    @child.command("items")
    def items():
        return [{"name": "apple"}, {"name": "banana"}]

    result = runner.invoke(app, ["child", "items"])
    assert result.exit_code == 0
    assert "- apple" in result.output
    assert "- banana" in result.output

    # Clean up module globals
    globals().pop("format_items", None)


# ---------------------------------------------------------------------------
# 5.3 — Nested sub-apps
# ---------------------------------------------------------------------------


def test_nested_subapps_two_levels():
    """root > admin > users list --json must work."""
    app = DuoApp(name="root")
    admin = typer.Typer(help="Admin commands")
    users = typer.Typer(help="User commands")
    admin.add_typer(users, name="users")
    app.add_typer(admin, name="admin")

    @users.command("list")
    def list_users():
        return [{"name": "Alice"}]

    result = runner.invoke(app, ["admin", "users", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == [{"name": "Alice"}]


def test_nested_subapps_mixed_types():
    """Root=DuoApp, middle=typer.Typer, leaf=DuoApp."""
    app = DuoApp(name="root")
    middle = typer.Typer(help="Middle layer")
    leaf = DuoApp(help="Leaf DuoApp")
    middle.add_typer(leaf, name="leaf")
    app.add_typer(middle, name="middle")

    @leaf.command("info")
    def info():
        return {"level": "leaf"}

    result = runner.invoke(app, ["middle", "leaf", "info", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["level"] == "leaf"


def test_nested_subapp_added_after_parent_mount():
    """Nested sub-app added to child AFTER child was added to parent."""
    app = DuoApp(name="root")
    admin = typer.Typer(help="Admin commands")
    app.add_typer(admin, name="admin")

    # Add nested sub-app after admin was already mounted
    users = typer.Typer(help="User commands")
    admin.add_typer(users, name="users")

    @users.command("list")
    def list_users():
        return [{"name": "Bob"}]

    result = runner.invoke(app, ["admin", "users", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == [{"name": "Bob"}]


# ---------------------------------------------------------------------------
# 5.4 — Opt-out (Option C)
# ---------------------------------------------------------------------------


def test_add_typer_duo_false():
    """add_typer(..., duo=False) skips wrapping — no --json flag."""
    app = DuoApp(name="root")
    child = typer.Typer(help="Unwrapped child")
    app.add_typer(child, name="child", duo=False)

    @child.command("hello")
    def hello():
        print("Hello!")

    result = runner.invoke(app, ["child", "hello"])
    assert result.exit_code == 0
    assert "Hello!" in result.output

    # --json should not be recognized
    result_json = runner.invoke(app, ["child", "hello", "--json"])
    assert result_json.exit_code != 0


def test_command_duo_false():
    """@app.command(duo=False) does not add --json."""
    app = DuoApp(name="root")

    @app.command(duo=False)
    def interactive():
        print("Interactive mode only")

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Interactive mode only" in result.output

    # --json should not be recognized
    result_json = runner.invoke(app, ["--json"])
    assert result_json.exit_code != 0


def test_command_duo_false_on_patched_child():
    """duo=False on individual commands in a patched child sub-app."""
    app = DuoApp(name="root")
    child = typer.Typer(help="Mixed child")
    app.add_typer(child, name="child")

    @child.command("wrapped")
    def wrapped():
        return {"data": True}

    @child.command("unwrapped", duo=False)
    def unwrapped():
        print("No JSON here")

    # Wrapped command should support --json
    result = runner.invoke(app, ["child", "wrapped", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"data": True}

    # Unwrapped command should NOT have --json
    result2 = runner.invoke(app, ["child", "unwrapped"])
    assert result2.exit_code == 0
    assert "No JSON here" in result2.output

    result3 = runner.invoke(app, ["child", "unwrapped", "--json"])
    assert result3.exit_code != 0


# ---------------------------------------------------------------------------
# 5.5 — No double-wrapping
# ---------------------------------------------------------------------------


def test_duoapp_child_not_double_wrapped():
    """DuoApp child added to DuoApp parent — only one --json flag."""
    app = DuoApp(name="root")
    child = DuoApp(help="Already a DuoApp")
    app.add_typer(child, name="child")

    @child.command("check")
    def check():
        return {"ok": True}

    result = runner.invoke(app, ["child", "check", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True}


# ---------------------------------------------------------------------------
# 5.6 — Mixed root and sub-app commands
# ---------------------------------------------------------------------------


def test_root_and_subapp_commands_coexist():
    app = DuoApp(name="root")

    @app.command()
    def status():
        return {"healthy": True}

    child = typer.Typer(help="DB commands")
    app.add_typer(child, name="db")

    @child.command("ping")
    def db_ping():
        return {"latency_ms": 12}

    result_root = runner.invoke(app, ["status", "--json"])
    assert result_root.exit_code == 0
    assert json.loads(result_root.output)["healthy"] is True

    result_child = runner.invoke(app, ["db", "ping", "--json"])
    assert result_child.exit_code == 0
    assert json.loads(result_child.output)["latency_ms"] == 12


# ---------------------------------------------------------------------------
# 5.7 — Integration test
# ---------------------------------------------------------------------------


def test_realistic_multi_subapp():
    """3 sub-apps (2 DuoApp, 1 plain Typer), 2 root commands, all with --json."""
    app = DuoApp(name="my-tool")

    @app.command()
    def status():
        return {"healthy": True}

    @app.command()
    def version():
        return {"version": "1.0.0"}

    # DuoApp sub-apps
    issues = DuoApp(help="Issues")
    app.add_typer(issues, name="issues")

    @issues.command("list")
    def issues_list():
        return [{"id": 1, "title": "Bug"}]

    vault = DuoApp(help="Vault")
    app.add_typer(vault, name="vault")

    @vault.command("search")
    def vault_search(query: str = "test"):
        return [{"file": "note.md", "score": 0.9}]

    # Plain Typer sub-app (auto-wrapped)
    streak = typer.Typer(help="Streak tracking")
    app.add_typer(streak, name="streak")

    @streak.command("show")
    def streak_show():
        return {"current": 5, "longest": 12}

    # Verify all commands
    for cmd, args, check_key, check_val in [
        ("status", [], "healthy", True),
        ("version", [], "version", "1.0.0"),
        ("issues list", [], None, None),
        ("vault search", ["--query", "hello"], None, None),
        ("streak show", [], "current", 5),
    ]:
        invoke_args = cmd.split() + ["--json"] + args
        result = runner.invoke(app, invoke_args)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"
        payload = json.loads(result.output)
        if check_key is not None:
            if isinstance(payload, list):
                payload = payload[0]
            assert payload[check_key] == check_val, f"{cmd}: {payload}"
