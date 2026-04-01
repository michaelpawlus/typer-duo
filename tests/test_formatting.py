from typer_duo.formatting import format_human


def test_format_none():
    assert format_human(None) is None


def test_format_string():
    assert format_human("hello world") == "hello world"


def test_format_list_of_strings():
    result = format_human(["a", "b", "c"])
    assert result == "a\nb\nc"


def test_format_empty_list():
    assert format_human([]) == ""


def test_format_dict():
    result = format_human({"name": "Alice", "age": 30})
    assert "name" in result
    assert "Alice" in result
    assert "age" in result
    assert "30" in result


def test_format_empty_dict():
    assert format_human({}) == ""


def test_format_list_of_dicts():
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
    ]
    result = format_human(data)
    assert "name" in result
    assert "Alice" in result
    assert "Bob" in result
    # Should have multiple lines (header + data rows)
    assert len(result.strip().splitlines()) >= 3


def test_format_object_with_duo_format():
    class MyResult:
        def __duo_format__(self):
            return "custom output"

    assert format_human(MyResult()) == "custom output"


def test_format_fallback_to_str():
    assert format_human(42) == "42"
