"""Regex and label rules for the synthetic invoice and receipt layouts.

The prose layout is intentionally outside this grammar. The mock provider in
`document_ai.llm` covers that wording so the fallback path has a real job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from document_ai.dates import parse_date
from document_ai.money import money, parse_amount
from document_ai.text import normalize_text

VENDOR_RE = re.compile(r"(?im)^(?:Vendor|From|Merchant)\s*:\s*(.+?)\s*$")
NUMBER_RE = re.compile(r"(?im)^(?:Invoice Number|No\.|Receipt)\s*:\s*(\S+)\s*$")
GENERIC_NUMBER_RE = re.compile(r"\b(INV-\d{4}-\d{4}|RCT-\d{5})\b")
ISSUE_RE = re.compile(r"(?im)^(?:Invoice Date|Date)\s*:\s*(.+?)\s*$")
DUE_RE = re.compile(r"(?im)^(?:Due Date|Due)\s*:\s*(.+?)\s*$")
CURRENCY_RE = re.compile(r"(?im)^Currency\s*:\s*(EUR|USD|GBP)\s*$")
VAT_RATE_RE = re.compile(r"(?im)^VAT Rate\s*:\s*(\d+(?:\.\d+)?)%\s*$")
AMOUNT_RES = {
    "subtotal": re.compile(r"(?im)^Subtotal\s*:\s*([0-9][0-9.,]*)\s*$"),
    "vat_amount": re.compile(r"(?im)^VAT Amount\s*:\s*([0-9][0-9.,]*)\s*$"),
    "total": re.compile(r"(?im)^Total\s*:\s*([0-9][0-9.,]*)\s*$"),
}
LABELED_ITEM_RE = re.compile(
    r"^-\s*(?P<desc>.+?)\s*\|\s*qty\s+(?P<qty>\d+(?:\.\d+)?)\s*\|\s*"
    r"unit\s+(?P<unit>[\d.,]+)\s*\|\s*amount\s+(?P<amt>[\d.,]+)\s*$",
    re.MULTILINE,
)
TABLE_ITEM_RE = re.compile(
    r"^(?P<desc>[^;\n]+?);\s*(?P<qty>\d+(?:\.\d+)?);\s*(?P<unit>[\d.,]+);\s*(?P<amt>[\d.,]+)\s*$",
    re.MULTILINE,
)
RECEIPT_ITEM_RE = re.compile(
    r"^(?P<qty>\d+(?:\.\d+)?)\s+x\s+(?P<desc>.+?)\s+@\s+(?P<unit>[\d.,]+)\s+=\s+(?P<amt>[\d.,]+)\s*$",
    re.MULTILINE,
)


@dataclass
class PartialExtraction:
    values: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def extract_with_rules(text: str) -> PartialExtraction:
    normalized = normalize_text(text)
    result = PartialExtraction()
    document_type, type_confidence = _document_type(normalized)
    if document_type is not None:
        _put(result, "document_type", document_type, type_confidence)

    vendor = _first(VENDOR_RE, normalized)
    if vendor:
        _put(result, "vendor", vendor, 0.95)

    number = _first(NUMBER_RE, normalized)
    number_confidence = 0.96
    if number is None:
        generic = GENERIC_NUMBER_RE.search(normalized)
        if generic:
            number = generic.group(1)
            number_confidence = 0.84
    if number:
        _put(result, "document_number", number, number_confidence)

    issue_raw = _first(ISSUE_RE, normalized)
    if issue_raw:
        _put_date(result, "issue_date", issue_raw, 0.94)
    due_raw = _first(DUE_RE, normalized)
    if due_raw:
        _put_date(result, "due_date", due_raw, 0.94)
    elif document_type == "receipt":
        _put(result, "due_date", None, 0.9)

    currency = _first(CURRENCY_RE, normalized)
    if currency:
        _put(result, "currency", currency.upper(), 0.95)

    items = _line_items(normalized, result.warnings)
    if items:
        consistent = all(_line_is_consistent(item) for item in items)
        _put(result, "line_items", items, 0.93 if consistent else 0.55)
        if not consistent:
            result.warnings.append("one or more line totals do not match quantity * unit price")
    else:
        result.warnings.append("no line items matched")

    for key, pattern in AMOUNT_RES.items():
        raw = _first(pattern, normalized)
        if raw is None:
            continue
        try:
            _put(result, key, parse_amount(raw), 0.94)
        except ValueError:
            result.warnings.append(f"could not parse {key}: {raw}")

    rate = _first(VAT_RATE_RE, normalized)
    if rate is not None:
        _put(result, "vat_rate", (Decimal(rate) / Decimal("100")), 0.94)
    return result


def _document_type(text: str) -> tuple[str | None, float]:
    if re.search(r"(?m)^INVOICE\s*$", text):
        return "invoice", 0.97
    if re.search(r"(?m)^RECEIPT\s*$", text):
        return "receipt", 0.97
    if re.search(r"(?i)\bthis invoice\b", text):
        return "invoice", 0.86
    return None, 0.0


def _line_items(text: str, warnings: list[str]) -> list[dict[str, Any]]:
    candidates = (
        _collect(LABELED_ITEM_RE, text, warnings),
        _collect(TABLE_ITEM_RE, text, warnings),
        _collect(RECEIPT_ITEM_RE, text, warnings),
    )
    best: list[dict[str, Any]] = []
    for items in candidates:
        if len(items) > len(best):
            best = items
    return best


def _collect(pattern: re.Pattern[str], text: str, warnings: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        description = match.group("desc").strip()
        if description.casefold() == "description":
            continue
        try:
            items.append(
                {
                    "description": description,
                    "quantity": Decimal(match.group("qty")),
                    "unit_price": parse_amount(match.group("unit")),
                    "line_total": parse_amount(match.group("amt")),
                }
            )
        except ValueError:
            warnings.append(f"skipped an unreadable line item: {match.group(0)}")
    return items


def _line_is_consistent(item: dict[str, Any]) -> bool:
    expected = money(Decimal(item["quantity"]) * Decimal(item["unit_price"]))
    return abs(expected - money(item["line_total"])) <= Decimal("0.01")


def _put(result: PartialExtraction, key: str, value: Any, confidence: float) -> None:
    result.values[key] = value
    result.confidence[key] = confidence


def _put_date(result: PartialExtraction, key: str, raw: str, confidence: float) -> None:
    try:
        _put(result, key, parse_date(raw), confidence)
    except ValueError:
        result.warnings.append(f"could not parse {key.replace('_', ' ')}: {raw}")


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return match.group(1).strip()
