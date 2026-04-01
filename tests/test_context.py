import io
import sys

from typer_duo.context import _set_json_mode, duo_print, is_interactive, is_json_mode


def test_json_mode_default_false():
    _set_json_mode(False)
    assert is_json_mode() is False


def test_json_mode_set_true():
    _set_json_mode(True)
    assert is_json_mode() is True
    _set_json_mode(False)  # reset


def test_is_interactive_non_tty(monkeypatch):
    _set_json_mode(False)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert is_interactive() is False


def test_is_interactive_with_json_mode(monkeypatch):
    _set_json_mode(True)
    # Even if stdin is a TTY, json mode means not interactive
    assert is_interactive() is False
    _set_json_mode(False)


def test_duo_print(capsys):
    duo_print("hello")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello" in captured.err
