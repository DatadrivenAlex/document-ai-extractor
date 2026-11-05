import json
from decimal import Decimal
from typing import Self

import pytest

from document_ai.errors import LLMProviderError
from document_ai.llm import MockLLMProvider, OpenAICompatibleProvider, extract_prose
from document_ai.render import render_text
from tests.factories import make_invoice, make_receipt


def test_mock_is_deterministic() -> None:
    text = render_text(make_invoice(), "prose", "iso")
    provider = MockLLMProvider()
    assert provider.extract(text) == provider.extract(text)


def test_mock_reads_prose_invoice() -> None:
    fields = make_invoice(currency="EUR")
    extracted = extract_prose(render_text(fields, "prose", "iso"))
    assert extracted["vendor"] == fields.vendor
    assert extracted["document_number"] == fields.document_number
    assert extracted["issue_date"] == fields.issue_date
    assert extracted["due_date"] == fields.due_date
    assert extracted["currency"] == "EUR"
    assert extracted["subtotal"] == fields.subtotal
    assert extracted["vat_rate"] == Decimal("0.19")
    assert extracted["vat_amount"] == fields.vat_amount
    assert extracted["total"] == fields.total
    assert extracted["line_items"][0]["description"] == "Notebook"


def test_mock_leaves_non_prose_to_rules() -> None:
    text = render_text(make_receipt(), "receipt", "iso")
    assert extract_prose(text) == {}


def test_openai_provider_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMProviderError, match="OPENAI_API_KEY"):
        OpenAICompatibleProvider.from_env()


def test_openai_provider_parses_a_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def read(self) -> bytes:
            content = {
                "currency": "EUR",
                "document_number": "INV-2024-0001",
                "document_type": "invoice",
                "due_date": "2024-02-01",
                "issue_date": "2024-01-02",
                "line_items": [
                    {
                        "description": "Cable",
                        "line_total": "10.00",
                        "quantity": "1",
                        "unit_price": "10.00",
                    }
                ],
                "subtotal": "10.00",
                "total": "11.90",
                "vat_amount": "1.90",
                "vat_rate": "0.19",
                "vendor": "Acme GmbH",
            }
            body = {"choices": [{"message": {"content": json.dumps(content)}}]}
            return json.dumps(body).encode()

    def fake_urlopen(request, timeout: float = 0):  # type: ignore[no-untyped-def]
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("document_ai.llm.urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="mock-model",
        timeout=5,
    )
    extracted = provider.extract("Invoice text")
    assert extracted["vendor"] == "Acme GmbH"
    assert extracted["total"] == "11.90"
    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["timeout"] == 5
