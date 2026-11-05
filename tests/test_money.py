from decimal import Decimal

import pytest

from document_ai.money import format_amount, format_qty, format_rate, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.50", Decimal("12.50")),
        ("12,50", Decimal("12.50")),
        ("12,5", Decimal("12.50")),
        ("1,234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("1.000,00", Decimal("1000.00")),
        ("1,234", Decimal("1234.00")),
        ("0,00", Decimal("0.00")),
        ("€ 9,90", Decimal("9.90")),
        ("$1,250.00", Decimal("1250.00")),
    ],
)
def test_parse_amount(raw: str, expected: Decimal) -> None:
    assert parse_amount(raw) == expected


def test_parse_amount_rejects_blank_and_words() -> None:
    with pytest.raises(ValueError):
        parse_amount("   ")
    with pytest.raises(ValueError):
        parse_amount("twelve")


@pytest.mark.parametrize(
    ("value", "currency"),
    [
        (Decimal("0"), "EUR"),
        (Decimal("9.90"), "EUR"),
        (Decimal("1250"), "EUR"),
        (Decimal("12000.5"), "USD"),
        (Decimal("1000"), "GBP"),
        (Decimal("2.80"), "GBP"),
    ],
)
def test_format_roundtrip(value: Decimal, currency: str) -> None:
    assert parse_amount(format_amount(value, currency)) == parse_amount(format_amount(value, "USD"))
    assert parse_amount(format_amount(value, currency)) == Decimal(value).quantize(Decimal("0.01"))


def test_format_examples() -> None:
    assert format_amount(Decimal("1250"), "EUR") == "1.250,00"
    assert format_amount(Decimal("1250"), "USD") == "1,250.00"
    assert format_amount(Decimal("9.9"), "EUR") == "9,90"
    assert format_rate(Decimal("0.19")) == "19%"
    assert format_rate(Decimal("0")) == "0%"
    assert format_rate(Decimal("0.2")) == "20%"
    assert format_qty(Decimal("2.00")) == "2"


def test_eur_and_usd_grouping_differ() -> None:
    assert format_amount(Decimal("1234.56"), "EUR") == "1.234,56"
    assert format_amount(Decimal("1234.56"), "GBP") == "1,234.56"
