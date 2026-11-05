"""Small valid documents for unit tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from document_ai.models import LineItem, ValidatedDocument


def make_invoice(**overrides: object) -> ValidatedDocument:
    item = LineItem(
        description="Notebook",
        quantity=Decimal("2"),
        unit_price=Decimal("4.20"),
        line_total=Decimal("8.40"),
    )
    data: dict[str, object] = {
        "currency": "EUR",
        "document_number": "INV-2024-0099",
        "document_type": "invoice",
        "due_date": date(2024, 5, 3),
        "issue_date": date(2024, 4, 3),
        "line_items": [item],
        "subtotal": Decimal("8.40"),
        "total": Decimal("10.00"),
        "vat_amount": Decimal("1.60"),
        "vat_rate": Decimal("0.19"),
        "vendor": "Danube Analytics",
    }
    data.update(overrides)
    return ValidatedDocument.model_validate(data)


def make_receipt(**overrides: object) -> ValidatedDocument:
    item = LineItem(
        description="Espresso",
        quantity=Decimal("1"),
        unit_price=Decimal("2.80"),
        line_total=Decimal("2.80"),
    )
    data: dict[str, object] = {
        "currency": "GBP",
        "document_number": "RCT-00042",
        "document_type": "receipt",
        "due_date": None,
        "issue_date": date(2024, 11, 2),
        "line_items": [item],
        "subtotal": Decimal("2.80"),
        "total": Decimal("3.36"),
        "vat_amount": Decimal("0.56"),
        "vat_rate": Decimal("0.20"),
        "vendor": "Cafe Lumen",
    }
    data.update(overrides)
    return ValidatedDocument.model_validate(data)
