import json

import typer
from typer.testing import CliRunner

from typer_duo import duo_command

runner = CliRunner()


def test_duo_command_json_mode():
    app = typer.Typer()

    @app.command()
    @duo_command
    def status(json_output: bool = typer.Option(False, "--json")):
        return {"healthy": True, "count": 5}

    result = runner.invoke(app, ["--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["healthy"] is True
    assert payload["count"] == 5


def test_duo_command_human_mode():
    app = typer.Typer()

    @app.command()
    @duo_command
    def status(json_output: bool = typer.Option(False, "--json")):
        return {"healthy": True}

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    # Human output goes to stderr, which CliRunner mixes together
    assert "healthy" in result.output


def test_duo_command_returns_none():
    app = typer.Typer()

    @app.command()
    @duo_command
    def noop(json_output: bool = typer.Option(False, "--json")):
        return None

    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_duo_command_raises_duo_error():
    from typer_duo import DuoError

    app = typer.Typer()

    @app.command()
    @duo_command
    def fail(json_output: bool = typer.Option(False, "--json")):
        raise DuoError("broken", code=1)

    result = runner.invoke(app, ["--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["error"] == "broken"
