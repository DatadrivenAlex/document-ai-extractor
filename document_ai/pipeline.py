"""Run text extraction, rules, the optional LLM fallback, and validation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from document_ai.llm import LLMProvider
from document_ai.models import (
    FIELD_NAMES,
    ExtractedDocument,
    ExtractionResult,
    validation_errors,
)
from document_ai.rules import extract_with_rules
from document_ai.text import extract_text

# Rule hits at or above this score are kept. Weaker or missing fields may be
# filled by the configured provider. The mock provider writes 0.74, which is
# below the cutoff, so it never overwrites a confident rule.
LLM_THRESHOLD = 0.8
LLM_FILL_CONFIDENCE = 0.74
MONEY_FIELDS = {"subtotal", "vat_amount", "total", "vat_rate"}


def extract_document(
    path: Path | str,
    *,
    llm: LLMProvider | None = None,
    confidence_threshold: float = LLM_THRESHOLD,
    include_raw_text: bool = True,
) -> ExtractionResult:
    extracted = extract_text(path)
    ruled = extract_with_rules(extracted.text)
    values: dict[str, Any] = dict(ruled.values)
    confidence: dict[str, float] = dict(ruled.confidence)
    warnings = [*extracted.warnings, *ruled.warnings]
    sources = _initial_sources(values)

    extractor_name = "rules"
    if llm is not None and _needs_llm(values, confidence, confidence_threshold):
        try:
            guessed = llm.extract(extracted.text)
        except Exception as exc:
            warnings.append(f"LLM fallback failed: {exc}")
        else:
            filled = _merge(values, confidence, sources, guessed, confidence_threshold)
            if filled:
                extractor_name = "rules+llm"
                warnings.append("LLM fallback filled: " + ", ".join(filled))

    for key in FIELD_NAMES:
        confidence.setdefault(key, 0.0)
        sources.setdefault(key, "none")

    document = _build_document(values, warnings)
    errors = validation_errors(document)
    rounded = {key: round(float(confidence.get(key, 0.0)), 4) for key in FIELD_NAMES}
    return ExtractionResult(
        document=document,
        confidence=rounded,
        field_sources={key: sources.get(key, "none") for key in FIELD_NAMES},
        overall_confidence=_overall(rounded, errors),
        validation_ok=not errors,
        validation_errors=errors,
        warnings=_unique(warnings),
        text_method=extracted.method,
        extractor=extractor_name,
        raw_text=extracted.text if include_raw_text else None,
    )


def _initial_sources(values: dict[str, Any]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key in FIELD_NAMES:
        if _present(values, key):
            sources[key] = "rules"
        else:
            sources[key] = "none"
    return sources


def _needs_llm(
    values: dict[str, Any],
    confidence: dict[str, float],
    threshold: float,
) -> bool:
    for key in FIELD_NAMES:
        if not _present(values, key) or confidence.get(key, 0.0) < threshold:
            return True
    return False


def _present(values: dict[str, Any], key: str) -> bool:
    if key not in values:
        return False
    value = values[key]
    if key == "due_date":
        return True
    if value is None or value == "" or value == []:
        return False
    return True


def _merge(
    values: dict[str, Any],
    confidence: dict[str, float],
    sources: dict[str, str],
    guessed: dict[str, Any],
    threshold: float,
) -> list[str]:
    filled: list[str] = []
    normalized = _normalize_payload(guessed)
    for key in FIELD_NAMES:
        if key not in normalized:
            continue
        guessed_value = normalized[key]
        if guessed_value is None and key != "due_date":
            continue
        if _present(values, key) and confidence.get(key, 0.0) >= threshold:
            continue
        values[key] = guessed_value
        confidence[key] = LLM_FILL_CONFIDENCE
        sources[key] = "llm"
        filled.append(key)
    return filled


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in FIELD_NAMES:
            continue
        if value is None:
            if key == "due_date":
                normalized[key] = None
            continue
        if key in MONEY_FIELDS:
            normalized[key] = _as_decimal(value)
        elif key == "line_items" and isinstance(value, list):
            normalized[key] = [_normalize_item(item) for item in value]
        else:
            normalized[key] = value
    return normalized


def _normalize_item(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        raw = item.model_dump()
    elif isinstance(item, dict):
        raw = item
    else:
        return item
    return {
        "description": raw.get("description", ""),
        "quantity": _as_decimal(raw.get("quantity", "0")),
        "unit_price": _as_decimal(raw.get("unit_price", "0")),
        "line_total": _as_decimal(raw.get("line_total", "0")),
    }


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _build_document(values: dict[str, Any], warnings: list[str]) -> ExtractedDocument:
    prepared = _prepare(values)
    try:
        return ExtractedDocument.model_validate(prepared)
    except ValidationError:
        warnings.append("some extracted values were dropped because they did not match the schema")
    salvaged: dict[str, Any] = {}
    for key in FIELD_NAMES:
        if key not in prepared:
            continue
        trial = {**salvaged, key: prepared[key]}
        try:
            ExtractedDocument.model_validate(trial)
        except ValidationError:
            continue
        salvaged[key] = prepared[key]
    return ExtractedDocument.model_validate(salvaged)


def _prepare(values: dict[str, Any]) -> dict[str, Any]:
    data = dict(values)
    items = data.get("line_items") or []
    prepared = []
    for item in items:
        if hasattr(item, "model_dump"):
            prepared.append(item.model_dump())
        else:
            prepared.append(item)
    data["line_items"] = prepared
    return data


def _overall(confidence: dict[str, float], errors: list[str]) -> float:
    mean = sum(confidence.get(key, 0.0) for key in FIELD_NAMES) / len(FIELD_NAMES)
    if errors:
        mean *= 0.5
    return round(mean, 4)


def _unique(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        ordered.append(warning)
    return ordered
