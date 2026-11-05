import pytest
from fastapi.testclient import TestClient

from document_ai.api import app
from document_ai.generator import generate_corpus

client = TestClient(app)


def test_root_and_health() -> None:
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["extract"] == "POST /v1/extract"
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert "tesseract" in body


def test_extract_pdf(tmp_path) -> None:
    document = generate_corpus(1, 1, tmp_path)[0]
    with document.pdf_path.open("rb") as handle:
        response = client.post(
            "/v1/extract",
            files={"file": (document.pdf_path.name, handle, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["validation_ok"] is True
    assert body["document"]["vendor"] == document.fields.vendor
    assert body["text_method"] == "pdfplumber"
    assert body["document"]["total"] == f"{document.fields.total:.2f}"


def test_extract_prose_with_mock_llm(tmp_path) -> None:
    document = generate_corpus(1, 4, tmp_path)[3]
    assert document.layout == "prose"
    with document.pdf_path.open("rb") as handle:
        rules = client.post(
            "/v1/extract",
            files={"file": (document.pdf_path.name, handle, "application/pdf")},
        )
    with document.pdf_path.open("rb") as handle:
        recovered = client.post(
            "/v1/extract?llm=mock",
            files={"file": (document.pdf_path.name, handle, "application/pdf")},
        )
    assert rules.status_code == 200
    assert rules.json()["document"]["vendor"] is None
    assert recovered.status_code == 200
    assert recovered.json()["validation_ok"] is True
    assert recovered.json()["document"]["vendor"] == document.fields.vendor
    assert recovered.json()["extractor"] == "rules+llm"


def test_rejects_unknown_type(tmp_path) -> None:
    response = client.post(
        "/v1/extract",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_rejects_empty_upload() -> None:
    response = client.post(
        "/v1/extract",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_image_without_tesseract_returns_422(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("document_ai.text.tesseract_available", lambda: False)
    document = generate_corpus(1, 1, tmp_path)[0]
    with document.png_path.open("rb") as handle:
        response = client.post(
            "/v1/extract",
            files={"file": (document.png_path.name, handle, "image/png")},
        )
    assert response.status_code == 422
    assert "Tesseract" in response.json()["detail"]


def test_openai_without_key_is_400(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    document = generate_corpus(1, 1, tmp_path)[0]
    with document.pdf_path.open("rb") as handle:
        response = client.post(
            "/v1/extract?llm=openai",
            files={"file": (document.pdf_path.name, handle, "application/pdf")},
        )
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]
