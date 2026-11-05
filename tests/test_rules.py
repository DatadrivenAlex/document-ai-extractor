from decimal import Decimal

from document_ai.money import parse_amount
from document_ai.render import render_text
from document_ai.rules import extract_with_rules
from tests.factories import make_invoice, make_receipt


def test_labeled_invoice_text() -> None:
    fields = make_invoice(currency="USD")
    parsed = extract_with_rules(render_text(fields, "labeled", "dmy_mon"))
    assert parsed.values["vendor"] == fields.vendor
    assert parsed.values["document_number"] == fields.document_number
    assert parsed.values["issue_date"] == fields.issue_date
    assert parsed.values["due_date"] == fields.due_date
    assert parsed.values["currency"] == "USD"
    assert parsed.values["total"] == fields.total
    assert parsed.values["vat_rate"] == Decimal("0.19")
    assert parsed.values["line_items"][0]["description"] == "Notebook"
    assert parsed.confidence["vendor"] >= 0.9


def test_table_invoice_parses_european_thousands() -> None:
    fields = make_invoice(
        currency="EUR",
        document_number="INV-2024-0100",
        line_items=[
            {
                "description": "Server migration",
                "quantity": Decimal("2"),
                "unit_price": Decimal("1250.00"),
                "line_total": Decimal("2500.00"),
            }
        ],
        subtotal=Decimal("2500.00"),
        total=Decimal("2975.00"),
        vat_amount=Decimal("475.00"),
        vat_rate=Decimal("0.19"),
    )
    text = render_text(fields, "table", "dmy_dot")
    assert "1.250,00" in text
    assert "2.975,00" in text
    parsed = extract_with_rules(text)
    assert parsed.values["vendor"] == "Danube Analytics"
    assert parsed.values["total"] == Decimal("2975.00")
    assert parsed.values["line_items"][0]["unit_price"] == Decimal("1250.00")
    assert parse_amount("2.975,00") == parsed.values["total"]


def test_receipt_text_has_no_due_date() -> None:
    fields = make_receipt()
    parsed = extract_with_rules(render_text(fields, "receipt", "iso"))
    assert parsed.values["document_type"] == "receipt"
    assert parsed.values["vendor"] == "Cafe Lumen"
    assert parsed.values["document_number"] == "RCT-00042"
    assert parsed.values["due_date"] is None
    assert parsed.confidence["due_date"] >= 0.8
    assert parsed.values["line_items"][0]["description"] == "Espresso"
    assert parsed.values["total"] == Decimal("3.36")


def test_prose_is_only_partially_extracted() -> None:
    fields = make_invoice()
    parsed = extract_with_rules(render_text(fields, "prose", "iso"))
    assert parsed.values["document_type"] == "invoice"
    assert parsed.values["document_number"] == fields.document_number
    assert "vendor" not in parsed.values
    assert "issue_date" not in parsed.values
    assert "subtotal" not in parsed.values
    assert "line_items" not in parsed.values
    assert any("no line items" in warning for warning in parsed.warnings)


def test_garbage_text_matches_nothing_useful() -> None:
    parsed = extract_with_rules("hello there\nnothing to invoice")
    assert "vendor" not in parsed.values
    assert "total" not in parsed.values
    assert parsed.warnings
