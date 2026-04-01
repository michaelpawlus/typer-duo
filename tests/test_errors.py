import json

import pytest

from typer_duo.context import _set_json_mode
from typer_duo.errors import DuoError


def test_duo_error_human_mode(capsys):
    _set_json_mode(False)
    err = DuoError("something broke", code=1)
    with pytest.raises(SystemExit) as exc_info:
        err.render()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "something broke" in captured.err
    assert captured.out == ""


def test_duo_error_human_mode_with_details(capsys):
    _set_json_mode(False)
    err = DuoError("db failed", code=1, details={"host": "localhost", "port": 5432})
    with pytest.raises(SystemExit):
        err.render()
    captured = capsys.readouterr()
    assert "db failed" in captured.err
    assert "host: localhost" in captured.err


def test_duo_error_json_mode(capsys):
    _set_json_mode(True)
    err = DuoError("something broke", code=2, details={"key": "val"})
    with pytest.raises(SystemExit) as exc_info:
        err.render()
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["error"] == "something broke"
    assert payload["code"] == 2
    assert payload["details"] == {"key": "val"}
    assert captured.err == ""
    _set_json_mode(False)


def test_duo_error_json_mode_no_details(capsys):
    _set_json_mode(True)
    err = DuoError("fail", code=1)
    with pytest.raises(SystemExit):
        err.render()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert "details" not in payload
    _set_json_mode(False)
