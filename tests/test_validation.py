from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from document_ai.models import ExtractedDocument, validation_errors
from tests.factories import make_invoice, make_receipt


def test_accepts_balanced_invoice_and_receipt() -> None:
    assert validation_errors(ExtractedDocument.model_validate(make_invoice().model_dump())) == []
    assert validation_errors(ExtractedDocument.model_validate(make_receipt().model_dump())) == []


def test_accepts_zero_vat() -> None:
    document = make_invoice(
        total=Decimal("8.40"),
        vat_amount=Decimal("0.00"),
        vat_rate=Decimal("0"),
    )
    assert validation_errors(ExtractedDocument.model_validate(document.model_dump())) == []


def test_rejects_total_mismatch() -> None:
    document = ExtractedDocument.model_validate(make_invoice().model_dump())
    document.total = Decimal("1.00")
    errors = validation_errors(document)
    assert any("total does not equal subtotal plus VAT" in error for error in errors)


def test_rejects_line_sum_mismatch() -> None:
    document = ExtractedDocument.model_validate(make_invoice().model_dump())
    document.subtotal = Decimal("99.00")
    errors = validation_errors(document)
    assert any("subtotal does not equal the sum of line items" in error for error in errors)


def test_rejects_vat_mismatch() -> None:
    document = ExtractedDocument.model_validate(make_invoice().model_dump())
    document.vat_amount = Decimal("0.10")
    document.total = Decimal("8.50")
    errors = validation_errors(document)
    assert any("VAT amount does not equal subtotal * VAT rate" in error for error in errors)


def test_rejects_line_arithmetic() -> None:
    document = ExtractedDocument.model_validate(make_invoice().model_dump())
    document.line_items[0].line_total = Decimal("1.00")
    document.subtotal = Decimal("1.00")
    document.vat_amount = Decimal("0.19")
    document.total = Decimal("1.19")
    errors = validation_errors(document)
    assert any("does not match quantity * unit price" in error for error in errors)


def test_rejects_due_before_issue() -> None:
    with pytest.raises(ValidationError, match="due date is before the issue date"):
        make_invoice(due_date=date(2024, 1, 1))


def test_rejects_impossible_year() -> None:
    with pytest.raises(ValidationError, match="outside the supported range"):
        make_invoice(issue_date=date(1890, 1, 1), due_date=date(1890, 2, 1))


def test_invoice_requires_due_date() -> None:
    with pytest.raises(ValidationError, match="invoice is missing a due date"):
        make_invoice(due_date=None)


def test_receipt_allows_missing_due_date() -> None:
    receipt = make_receipt()
    assert receipt.due_date is None
