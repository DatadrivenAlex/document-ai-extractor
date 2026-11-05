"""Parse and format currency amounts used by the synthetic corpus."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.01")
TOLERANCE = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Quantize to cents with half-up rounding, the usual currency rule."""
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def format_amount(value: Decimal, currency: str) -> str:
    """Format cents for the synthetic documents.

    EUR uses European grouping (`1.234,56`). USD and GBP use US grouping
    (`1,234.56`). Real UK documents often use the US style; the corpus follows
    that, and only EUR uses the comma decimal mark.
    """
    quantized = money(value)
    sign = "-" if quantized < 0 else ""
    whole, frac = f"{abs(quantized):.2f}".split(".")
    groups: list[str] = []
    rest = whole
    while rest:
        groups.append(rest[-3:])
        rest = rest[:-3]
    body = ".".join(reversed(groups)) if currency == "EUR" else ",".join(reversed(groups))
    separator = "," if currency == "EUR" else "."
    return f"{sign}{body}{separator}{frac}"


def format_rate(rate: Decimal) -> str:
    """Format a fractional VAT rate as a percent, such as `19%` or `7.5%`."""
    percent = (Decimal(rate) * Decimal("100")).normalize()
    text = format(percent, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%"


def format_qty(quantity: Decimal) -> str:
    text = format(Decimal(quantity).normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_amount(value: str) -> Decimal:
    """Parse a money token into cents.

    The rightmost `.` or `,` is the decimal mark when both appear, so
    `1,234.56` and `1.234,56` both become `1234.56`. A comma alone is a
    decimal mark when the tail has one or two digits (`12,50`) and a thousands
    separator when it groups digits by three (`1,234`).
    """
    cleaned = value.strip().replace(" ", "").replace("\u00a0", "")
    if not cleaned:
        raise ValueError("empty amount")
    for token in ("EUR", "USD", "GBP", "€", "$", "£"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    sign = Decimal("-1") if cleaned.startswith("-") else Decimal("1")
    if cleaned[0] in "+-":
        cleaned = cleaned[1:]
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", cleaned):
        raise ValueError(f"not an amount: {value}")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            normalized = cleaned.replace(".", "").replace(",", ".")
        else:
            normalized = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", cleaned):
            normalized = cleaned.replace(",", "")
        else:
            whole, frac = cleaned.split(",", 1)
            if not frac or len(frac) > 2 or "," in frac:
                raise ValueError(f"not an amount: {value}")
            normalized = f"{whole}.{frac}"
    else:
        normalized = cleaned
    return money(sign * Decimal(normalized))
