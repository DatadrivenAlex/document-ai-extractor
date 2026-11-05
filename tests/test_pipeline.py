from decimal import Decimal

import pytest

from document_ai.errors import LLMProviderError
from document_ai.llm import MockLLMProvider
from document_ai.pipeline import extract_document
from document_ai.render import render_pdf, render_text
from tests.factories import make_invoice, make_receipt


class _ExplodingProvider:
    name = "explode"

    def extract(self, text: str) -> dict[str, object]:
        raise AssertionError(f"provider should not be called for {text[:40]!r}")


class _FailingProvider:
    name = "fail"

    def extract(self, text: str) -> dict[str, object]:
        raise LLMProviderError("provider down")


def _pdf(tmp_path, fields, layout: str, style: str):
    text = render_text(fields, layout, style)
    path = tmp_path / f"{layout}.pdf"
    render_pdf(text.splitlines(), path)
    return path


def test_labeled_pdf_does_not_need_the_provider(tmp_path) -> None:
    path = _pdf(tmp_path, make_invoice(currency="USD"), "labeled", "iso")
    result = extract_document(path, llm=_ExplodingProvider())
    assert result.validation_ok is True
    assert result.extractor == "rules"
    assert result.text_method == "pdfplumber"
    assert result.document.vendor == "Danube Analytics"
    assert result.document.total == Decimal("10.00")
    assert result.field_sources["vendor"] == "rules"
    assert 0.8 <= result.overall_confidence <= 1


def test_table_pdf_reads_european_thousands(tmp_path) -> None:
    fields = make_invoice(
        currency="EUR",
        line_items=[
            {
                "description": "Annual support",
                "line_total": Decimal("2400.00"),
                "quantity": Decimal("1"),
                "unit_price": Decimal("2400.00"),
            }
        ],
        subtotal=Decimal("2400.00"),
        total=Decimal("2520.00"),
        vat_amount=Decimal("120.00"),
        vat_rate=Decimal("0.05"),
    )
    result = extract_document(_pdf(tmp_path, fields, "table", "dmy_dot"))
    assert result.validation_ok is True
    assert result.document.total == Decimal("2520.00")
    assert result.document.line_items[0].unit_price == Decimal("2400.00")
    assert result.document.issue_date == fields.issue_date


def test_receipt_pdf_roundtrip(tmp_path) -> None:
    fields = make_receipt()
    result = extract_document(_pdf(tmp_path, fields, "receipt", "dmy_mon"))
    assert result.validation_ok is True
    assert result.document.document_type == "receipt"
    assert result.document.due_date is None
    assert result.document.vendor == fields.vendor
    assert result.document.total == fields.total
    assert result.field_sources["due_date"] == "rules"


def test_prose_rules_miss_vendor_and_mock_recovers_it(tmp_path) -> None:
    fields = make_invoice()
    path = _pdf(tmp_path, fields, "prose", "iso")
    rules_only = extract_document(path)
    assert rules_only.document.vendor is None
    assert rules_only.validation_ok is False
    assert rules_only.overall_confidence < 0.5
    assert rules_only.document.document_number == fields.document_number

    recovered = extract_document(path, llm=MockLLMProvider())
    assert recovered.validation_ok is True
    assert recovered.extractor == "rules+llm"
    assert recovered.document.vendor == fields.vendor
    assert recovered.document.issue_date == fields.issue_date
    assert recovered.document.due_date == fields.due_date
    assert recovered.document.total == fields.total
    assert recovered.document.line_items[0].description == "Notebook"
    assert recovered.field_sources["vendor"] == "llm"
    assert recovered.field_sources["document_number"] == "rules"
    assert any("LLM fallback filled" in warning for warning in recovered.warnings)


def test_llm_failure_is_a_warning(tmp_path) -> None:
    path = _pdf(tmp_path, make_invoice(), "prose", "iso")
    result = extract_document(path, llm=_FailingProvider())
    assert result.document.vendor is None
    assert any("provider down" in warning for warning in result.warnings)


def test_garbage_pdf_does_not_raise(tmp_path) -> None:
    path = tmp_path / "notes.pdf"
    render_pdf(["hello there", "nothing to invoice"], path)
    result = extract_document(path)
    assert result.validation_ok is False
    assert result.document.vendor is None
    assert result.confidence["vendor"] == 0


def test_confidence_scores_stay_inside_zero_and_one(tmp_path) -> None:
    path = _pdf(tmp_path, make_invoice(), "labeled", "iso")
    result = extract_document(path)
    assert set(result.confidence) == {
        "currency",
        "document_number",
        "document_type",
        "due_date",
        "issue_date",
        "line_items",
        "subtotal",
        "total",
        "vat_amount",
        "vat_rate",
        "vendor",
    }
    assert all(0 <= score <= 1 for score in result.confidence.values())


@pytest.mark.parametrize("style", ["iso", "dmy_dot", "dmy_mon"])
def test_labeled_dates_roundtrip(tmp_path, style: str) -> None:
    fields = make_invoice()
    result = extract_document(_pdf(tmp_path, fields, "labeled", style))
    assert result.document.issue_date == fields.issue_date
    assert result.document.due_date == fields.due_date
