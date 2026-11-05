"""Score the extractor against a seeded synthetic corpus."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from document_ai.generator import GeneratedDocument, generate_corpus
from document_ai.llm import MockLLMProvider
from document_ai.models import FIELD_NAMES, ExtractedDocument, LineItem, ValidatedDocument
from document_ai.money import TOLERANCE, money
from document_ai.pipeline import extract_document

FIELD_LABELS = {
    "document_type": "Document type",
    "vendor": "Vendor",
    "document_number": "Invoice / receipt number",
    "issue_date": "Issue date",
    "due_date": "Due date",
    "currency": "Currency",
    "subtotal": "Subtotal",
    "vat_rate": "VAT rate",
    "vat_amount": "VAT amount",
    "total": "Total",
    "line_items": "Line items",
}

RATE_TOLERANCE = Decimal("0.0001")


def run_evaluation(seed: int = 42, count: int = 40, dest_dir: Path | None = None) -> dict[str, Any]:
    """Extract each generated PDF and score it. The corpus is digital PDF text, not OCR."""
    if dest_dir is None:
        raise ValueError("dest_dir is required so generated files stay out of the repo root")
    documents = generate_corpus(seed=seed, count=count, dest_dir=dest_dir)
    layout_counts = dict(sorted(Counter(document.layout for document in documents).items()))
    report: dict[str, Any] = {
        "count": count,
        "layout_counts": layout_counts,
        "modes": {
            "rules": _score(documents, llm=None),
            "rules_plus_mock_llm": _score(documents, llm=MockLLMProvider()),
        },
        "notes": (
            "Exact-match accuracy on seeded synthetic digital PDFs. "
            "The prose layout is outside the rule grammar and is recovered by the mock "
            "provider, which is a deterministic parser rather than a neural model. "
            "These numbers are not a measurement on real vendor invoices."
        ),
        "seed": seed,
        "text_source": "digital PDF via pdfplumber",
    }
    report["markdown"] = render_markdown(report)
    return report


def compare_documents(predicted: ExtractedDocument, truth: ValidatedDocument) -> dict[str, bool]:
    return {field: _field_matches(field, predicted, truth) for field in FIELD_NAMES}


def render_markdown(report: dict[str, Any]) -> str:
    layout_bits = ", ".join(f"{count} {name}" for name, count in report["layout_counts"].items())
    rules = report["modes"]["rules"]
    mock = report["modes"]["rules_plus_mock_llm"]
    lines = [
        (
            f"Corpus: seed {report['seed']}, {report['count']} digital PDFs "
            f"({layout_bits}), text via pdfplumber. "
            "Rules only versus rules plus the deterministic mock provider."
        ),
        "",
        "| Field | Rules only | Rules + mock LLM |",
        "| --- | --- | --- |",
    ]
    for field in FIELD_NAMES:
        lines.append(
            f"| {FIELD_LABELS[field]} | {_cell(rules['field_accuracy'][field])} | "
            f"{_cell(mock['field_accuracy'][field])} |"
        )
    lines.append(
        f"| All field checks | {_cell(rules['field_checks'])} | {_cell(mock['field_checks'])} |"
    )
    lines.append(
        "| Document exact match | "
        f"{_cell(rules['document_exact_match'])} | {_cell(mock['document_exact_match'])} |"
    )
    lines.append(
        "| Validation pass | "
        f"{_cell(rules['validation_pass'])} | {_cell(mock['validation_pass'])} |"
    )
    lines.extend(
        [
            "",
            "| Layout | Documents | Rules exact | Mock exact |",
            "| --- | --- | --- | --- |",
        ]
    )
    for layout, count in report["layout_counts"].items():
        lines.append(
            f"| {layout} | {count} | "
            f"{_cell(rules['per_layout'][layout]['document_exact_match'])} | "
            f"{_cell(mock['per_layout'][layout]['document_exact_match'])} |"
        )
    lines.extend(
        [
            "",
            "These figures are exact-match scores on the synthetic corpus above. "
            "They are not a measurement on real vendor invoices. "
            "The prose layout is outside the rule grammar; the mock provider is a "
            "deterministic parser for that wording, not a neural model.",
        ]
    )
    return "\n".join(lines)


def _score(documents: list[GeneratedDocument], llm: MockLLMProvider | None) -> dict[str, Any]:
    counts = {field: {"correct": 0, "total": 0} for field in FIELD_NAMES}
    per_layout: dict[str, dict[str, int]] = {}
    failures: list[dict[str, Any]] = []
    exact = 0
    valid = 0
    for document in documents:
        result = extract_document(document.pdf_path, llm=llm, include_raw_text=False)
        matches = compare_documents(result.document, document.fields)
        bucket = per_layout.setdefault(document.layout, {"documents": 0, "exact": 0, "valid": 0})
        bucket["documents"] += 1
        if result.validation_ok:
            valid += 1
            bucket["valid"] += 1
        if all(matches.values()):
            exact += 1
            bucket["exact"] += 1
        for field, ok in matches.items():
            counts[field]["total"] += 1
            if ok:
                counts[field]["correct"] += 1
                continue
            failures.append(
                {
                    "actual": _show(getattr(result.document, field)),
                    "expected": _show(getattr(document.fields, field)),
                    "field": field,
                    "id": document.id,
                    "layout": document.layout,
                }
            )
    total_docs = len(documents)
    field_accuracy = {field: _ratio(row["correct"], row["total"]) for field, row in counts.items()}
    field_checks = _ratio(
        sum(row["correct"] for row in field_accuracy.values()),
        sum(row["total"] for row in field_accuracy.values()),
    )
    layouts = {
        layout: {
            "document_exact_match": _ratio(raw["exact"], raw["documents"]),
            "documents": raw["documents"],
            "validation_pass": _ratio(raw["valid"], raw["documents"]),
        }
        for layout, raw in sorted(per_layout.items())
    }
    return {
        "document_exact_match": _ratio(exact, total_docs),
        "failures": failures,
        "field_accuracy": field_accuracy,
        "field_checks": field_checks,
        "per_layout": layouts,
        "validation_pass": _ratio(valid, total_docs),
    }


def _field_matches(field: str, predicted: ExtractedDocument, truth: ValidatedDocument) -> bool:
    actual = getattr(predicted, field)
    expected = getattr(truth, field)
    if field in {"vendor", "document_number"}:
        return _norm_text(actual) == _norm_text(expected)
    if field in {"document_type", "currency", "issue_date", "due_date"}:
        return actual == expected
    if field == "vat_rate":
        return _close(actual, expected, RATE_TOLERANCE)
    if field in {"subtotal", "vat_amount", "total"}:
        return _close(actual, expected, TOLERANCE)
    if field == "line_items":
        return _lines_match(actual, expected)
    raise AssertionError(field)


def _lines_match(actual: list[LineItem], expected: list[LineItem]) -> bool:
    actual_keys = Counter(_line_key(item) for item in actual)
    expected_keys = Counter(_line_key(item) for item in expected)
    return actual_keys == expected_keys


def _line_key(item: LineItem) -> tuple[str, Decimal, Decimal, Decimal]:
    return (
        _norm_text(item.description) or "",
        Decimal(item.quantity),
        money(item.unit_price),
        money(item.line_total),
    )


def _close(actual: Decimal | None, expected: Decimal | None, tolerance: Decimal) -> bool:
    if actual is None or expected is None:
        return False
    return abs(Decimal(actual) - Decimal(expected)) <= tolerance


def _norm_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.casefold().split())


def _ratio(correct: int, total: int) -> dict[str, Any]:
    accuracy = 0.0 if total == 0 else round(correct / total, 4)
    return {"accuracy": accuracy, "correct": correct, "total": total}


def _cell(row: dict[str, Any]) -> str:
    correct = int(row["correct"])
    total = int(row["total"])
    percent = 0.0 if total == 0 else (100 * correct / total)
    return f"{correct}/{total} ({percent:.1f}%)"


def _show(value: Any) -> Any:
    if isinstance(value, list):
        shown = []
        for item in value:
            if isinstance(item, LineItem):
                shown.append(item.model_dump(mode="json"))
            else:
                shown.append(item)
        return shown
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return value
