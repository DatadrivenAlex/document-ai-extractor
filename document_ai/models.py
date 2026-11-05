"""Pydantic models for extracted documents, validation, and API responses."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from document_ai.dates import year_is_sane
from document_ai.money import TOLERANCE, money

FIELD_NAMES: tuple[str, ...] = (
    "document_type",
    "vendor",
    "document_number",
    "issue_date",
    "due_date",
    "currency",
    "subtotal",
    "vat_rate",
    "vat_amount",
    "total",
    "line_items",
)

CurrencyCode = Literal["EUR", "USD", "GBP"]
DocumentType = Literal["invoice", "receipt"]


class LineItem(BaseModel):
    """One billed row. Arithmetic is checked on the validated document, not here."""

    model_config = ConfigDict(extra="ignore")

    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class ExtractedDocument(BaseModel):
    """Loose extraction payload. Missing fields stay null so a bad scan still returns JSON."""

    model_config = ConfigDict(extra="ignore")

    document_type: DocumentType | None = None
    vendor: str | None = None
    document_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: CurrencyCode | None = None
    subtotal: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_amount: Decimal | None = None
    total: Decimal | None = None
    line_items: list[LineItem] = Field(default_factory=list)


class ValidatedDocument(BaseModel):
    """Ground truth and any extraction that claims to be a complete document."""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    vendor: str = Field(min_length=1)
    document_number: str = Field(min_length=1)
    issue_date: date
    due_date: date | None = None
    currency: CurrencyCode
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    line_items: list[LineItem] = Field(min_length=1)

    @model_validator(mode="after")
    def check_totals_and_dates(self) -> ValidatedDocument:
        problems = consistency_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def consistency_problems(document: ExtractedDocument | ValidatedDocument) -> list[str]:
    """Return human-readable invariant failures.

    Totals must match the line items plus VAT, each line total must match
    quantity times unit price, and dates must be ordered and inside 1990-2100.
    """
    problems: list[str] = []
    if document.issue_date is not None and not year_is_sane(document.issue_date):
        problems.append("issue date is outside the supported range (1990-2100)")
    if document.due_date is not None and not year_is_sane(document.due_date):
        problems.append("due date is outside the supported range (1990-2100)")
    if (
        document.issue_date is not None
        and document.due_date is not None
        and document.due_date < document.issue_date
    ):
        problems.append("due date is before the issue date")
    if document.document_type == "invoice" and document.due_date is None:
        problems.append("invoice is missing a due date")

    for index, item in enumerate(document.line_items, start=1):
        if item.quantity <= 0:
            problems.append(f"line {index} quantity must be positive")
        if item.unit_price < 0 or item.line_total < 0:
            problems.append(f"line {index} amounts must not be negative")
        expected = money(item.quantity * item.unit_price)
        if abs(expected - money(item.line_total)) > TOLERANCE:
            problems.append(f"line {index} total does not match quantity * unit price")

    if document.line_items and document.subtotal is not None:
        line_sum = money(sum((item.line_total for item in document.line_items), Decimal("0")))
        if abs(line_sum - money(document.subtotal)) > TOLERANCE:
            problems.append("subtotal does not equal the sum of line items")

    if (
        document.subtotal is not None
        and document.vat_rate is not None
        and document.vat_amount is not None
    ):
        expected_vat = money(document.subtotal * document.vat_rate)
        if abs(expected_vat - money(document.vat_amount)) > TOLERANCE:
            problems.append("VAT amount does not equal subtotal * VAT rate")

    if (
        document.subtotal is not None
        and document.vat_amount is not None
        and document.total is not None
        and abs(money(document.subtotal + document.vat_amount) - money(document.total)) > TOLERANCE
    ):
        problems.append("total does not equal subtotal plus VAT")

    if document.subtotal is not None and document.subtotal < 0:
        problems.append("subtotal must not be negative")
    if document.vat_rate is not None and (
        document.vat_rate < 0 or document.vat_rate > Decimal("1")
    ):
        problems.append("VAT rate must be a fraction between 0 and 1")
    return problems


def validation_errors(document: ExtractedDocument) -> list[str]:
    """Validate a loose extraction with the strict Pydantic model."""
    try:
        ValidatedDocument.model_validate(document.model_dump())
    except ValidationError as exc:
        messages: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            msg = str(error["msg"])
            messages.append(f"{loc}: {msg}" if loc else msg)
        return messages
    return []


class ExtractionResult(BaseModel):
    """What the CLI and HTTP API return for one document."""

    document: ExtractedDocument
    confidence: dict[str, float]
    field_sources: dict[str, str]
    overall_confidence: float
    validation_ok: bool
    validation_errors: list[str]
    warnings: list[str]
    text_method: str
    extractor: str
    raw_text: str | None = None
