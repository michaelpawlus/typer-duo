from typer_duo.constants import EXIT_ERROR, EXIT_NOT_FOUND, EXIT_OK


def test_exit_codes():
    assert EXIT_OK == 0
    assert EXIT_ERROR == 1
    assert EXIT_NOT_FOUND == 2
