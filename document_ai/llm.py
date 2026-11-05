"""Pluggable LLM fallback.

`MockLLMProvider` is a deterministic offline parser for the prose layout. It
stands in for a model in tests and in the evaluation. `OpenAICompatibleProvider`
calls a chat-completions endpoint only when an API key is set; the test suite
never uses a paid key.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from decimal import Decimal
from typing import Any, Protocol

from document_ai.dates import parse_date
from document_ai.errors import LLMProviderError
from document_ai.money import parse_amount
from document_ai.rules import extract_with_rules
from document_ai.text import normalize_text

PROSE_ITEM_RE = re.compile(
    r'Bought\s+(?P<qty>\d+(?:\.\d+)?)\s+of\s+"(?P<desc>[^"]+)"\s+priced at\s+'
    r"(?P<unit>[\d.,]+)\s+each\s+\(line\s+(?P<amt>[\d.,]+)\)\."
)


class LLMProvider(Protocol):
    """Something that turns document text into a partial field dict."""

    name: str

    def extract(self, text: str) -> dict[str, Any]:
        """Return field values. Implementations used in tests must be deterministic."""


class MockLLMProvider:
    """Offline fallback. Prose wording is parsed here; other layouts reuse the rules."""

    name = "mock"

    def extract(self, text: str) -> dict[str, Any]:
        prose = extract_prose(text)
        if prose.get("vendor"):
            return prose
        return extract_with_rules(text).values


class OpenAICompatibleProvider:
    """Optional HTTP provider. Disabled unless `OPENAI_API_KEY` is set."""

    name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> OpenAICompatibleProvider:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise LLMProviderError(
                "OPENAI_API_KEY is not set. Use --llm mock for the offline fallback."
            )
        timeout = float(os.environ.get("OPENAI_TIMEOUT", "30"))
        return cls(
            api_key=key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            timeout=timeout,
        )

    def extract(self, text: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract an invoice or receipt. Return one JSON object with keys "
                        "document_type, vendor, document_number, issue_date, due_date, "
                        "currency, subtotal, vat_rate, vat_amount, total, and line_items. "
                        "Dates are YYYY-MM-DD. due_date is null on a receipt. vat_rate is "
                        "a fraction such as 0.19. Money values are decimal strings. "
                        "line_items is a list of description, quantity, unit_price, line_total. "
                        "Use null when a field is absent."
                    ),
                },
                {"role": "user", "content": text},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise LLMProviderError(f"LLM request failed: {exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("LLM response did not include message content") from exc
        return _parse_json_object(content)


def build_provider(name: str) -> LLMProvider | None:
    normalized = name.strip().lower()
    if normalized in {"", "none", "off"}:
        return None
    if normalized == "mock":
        return MockLLMProvider()
    if normalized == "openai":
        return OpenAICompatibleProvider.from_env()
    raise LLMProviderError(f"unknown LLM provider '{name}'. Choose none, mock, or openai.")


def extract_prose(text: str) -> dict[str, Any]:
    """Parse the generator's prose layout. Returns an empty dict for other layouts."""
    normalized = normalize_text(text)
    vendor_match = re.search(r"(?i)this invoice was issued by\s+(.+?)\.", normalized)
    if vendor_match is None:
        return {}
    values: dict[str, Any] = {
        "document_type": "invoice",
        "vendor": vendor_match.group(1).strip(),
    }
    number = re.search(r"Reference code\s+([A-Z]+-[\d-]+)\.", normalized)
    if number:
        values["document_number"] = number.group(1)
    issue = re.search(r"Issued on\s+(\d{1,2} [A-Za-z]+ \d{4})\.", normalized)
    if issue:
        values["issue_date"] = parse_date(issue.group(1))
    due = re.search(r"Payment is due on\s+(\d{1,2} [A-Za-z]+ \d{4})\.", normalized)
    if due:
        values["due_date"] = parse_date(due.group(1))
    currency = re.search(r"Amounts are in\s+(EUR|USD|GBP)\.", normalized)
    if currency:
        values["currency"] = currency.group(1)
    net = re.search(r"The net amount is\s+([0-9][0-9.,]*)\.", normalized)
    if net:
        values["subtotal"] = parse_amount(net.group(1))
    vat = re.search(
        r"Value added tax at\s+(\d+(?:\.\d+)?)%\s+comes to\s+([0-9][0-9.,]*)\.",
        normalized,
    )
    if vat:
        values["vat_rate"] = Decimal(vat.group(1)) / Decimal("100")
        values["vat_amount"] = parse_amount(vat.group(2))
    total = re.search(r"The grand total is\s+([0-9][0-9.,]*)\.", normalized)
    if total:
        values["total"] = parse_amount(total.group(1))
    items = []
    for match in PROSE_ITEM_RE.finditer(normalized):
        items.append(
            {
                "description": match.group("desc").strip(),
                "quantity": Decimal(match.group("qty")),
                "unit_price": parse_amount(match.group("unit")),
                "line_total": parse_amount(match.group("amt")),
            }
        )
    if items:
        values["line_items"] = items
    return values


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM response was not valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("LLM response JSON must be an object")
    return data
