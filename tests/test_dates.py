from datetime import date

import pytest

from document_ai.dates import format_date, parse_date


def test_parse_supported_formats() -> None:
    assert parse_date("2024-04-03") == date(2024, 4, 3)
    assert parse_date("03.04.2024") == date(2024, 4, 3)
    assert parse_date("03 Apr 2024") == date(2024, 4, 3)
    assert parse_date("3 April 2024") == date(2024, 4, 3)


def test_format_styles_roundtrip() -> None:
    value = date(2025, 1, 9)
    for style in ("iso", "dmy_dot", "dmy_mon", "long"):
        assert parse_date(format_date(value, style)) == value


def test_parse_rejects_impossible_and_unknown() -> None:
    with pytest.raises(ValueError):
        parse_date("2024-02-31")
    with pytest.raises(ValueError):
        parse_date("32.01.2024")
    with pytest.raises(ValueError):
        parse_date("sometime next week")
