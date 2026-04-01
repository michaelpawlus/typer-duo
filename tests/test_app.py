import json

from typer.testing import CliRunner

from typer_duo import DuoApp, DuoError

runner = CliRunner()


def test_duo_app_json_mode():
    app = DuoApp(name="test-tool")

    @app.command()
    def status():
        return {"healthy": True, "uptime_seconds": 12345}

    result = runner.invoke(app, ["--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["healthy"] is True
    assert payload["uptime_seconds"] == 12345


def test_duo_app_human_mode():
    app = DuoApp(name="test-tool")

    @app.command()
    def greet(name: str):
        return {"message": f"Hello, {name}!"}

    result = runner.invoke(app, ["Alice"])
    assert result.exit_code == 0
    assert "Hello, Alice!" in result.output


def test_duo_app_returns_none():
    app = DuoApp(name="test-tool")

    @app.command()
    def noop():
        return None

    result = runner.invoke(app, [])
    assert result.exit_code == 0


def test_duo_app_returns_list_of_dicts():
    app = DuoApp(name="test-tool")

    @app.command()
    def users():
        return [{"name": "Alice", "role": "admin"}, {"name": "Bob", "role": "user"}]

    result = runner.invoke(app, ["--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload) == 2
    assert payload[0]["name"] == "Alice"


def test_duo_app_returns_string():
    app = DuoApp(name="test-tool")

    @app.command()
    def hello():
        return "Hello world"

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Hello world" in result.output


def test_duo_app_duo_error_json():
    app = DuoApp(name="test-tool")

    @app.command()
    def fail():
        raise DuoError("something broke", code=2, details={"reason": "unknown"})

    result = runner.invoke(app, ["--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "something broke"
    assert payload["code"] == 2
    assert payload["details"]["reason"] == "unknown"


def test_duo_app_duo_error_human():
    app = DuoApp(name="test-tool")

    @app.command()
    def fail():
        raise DuoError("something broke", code=1)

    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "something broke" in result.output


def test_duo_app_multiple_commands():
    app = DuoApp(name="test-tool")

    @app.command()
    def cmd_a():
        return {"from": "a"}

    @app.command()
    def cmd_b():
        return {"from": "b"}

    result_a = runner.invoke(app, ["cmd-a", "--json"])
    assert json.loads(result_a.output)["from"] == "a"

    result_b = runner.invoke(app, ["cmd-b", "--json"])
    assert json.loads(result_b.output)["from"] == "b"


def test_duo_app_with_arguments():
    app = DuoApp(name="test-tool")

    @app.command()
    def greet(name: str, greeting: str = "Hello"):
        return {"message": f"{greeting}, {name}!"}

    result = runner.invoke(app, ["Alice", "--greeting", "Hi", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["message"] == "Hi, Alice!"
