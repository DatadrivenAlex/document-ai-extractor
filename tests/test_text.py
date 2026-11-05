import shutil

import pytest
from reportlab.pdfgen import canvas

from document_ai.errors import TesseractNotAvailableError, UnsupportedFileTypeError
from document_ai.generator import generate_corpus
from document_ai.pipeline import extract_document
from document_ai.render import render_pdf, render_png, render_text
from document_ai.text import extract_text, tesseract_available
from tests.factories import make_invoice


def test_pdf_text_matches_the_rendered_lines(tmp_path) -> None:
    fields = make_invoice()
    text = render_text(fields, "labeled", "iso")
    pdf_path = tmp_path / "invoice.pdf"
    render_pdf(text.splitlines(), pdf_path)
    extracted = extract_text(pdf_path)
    assert extracted.method == "pdfplumber"
    assert extracted.text == text
    assert fields.vendor in extracted.text


def test_blank_pdf_warns(tmp_path) -> None:
    path = tmp_path / "blank.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.showPage()
    pdf.save()
    extracted = extract_text(path)
    assert extracted.text == ""
    assert extracted.warnings


def test_unsupported_extension(tmp_path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFileTypeError):
        extract_text(path)


def test_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "missing.pdf")


def test_image_without_tesseract(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("document_ai.text.tesseract_available", lambda: False)
    document = generate_corpus(1, 1, tmp_path)[0]
    with pytest.raises(TesseractNotAvailableError):
        extract_text(document.png_path)


@pytest.mark.skipif(not tesseract_available(), reason="tesseract binary is not installed")
def test_ocr_reads_a_labeled_invoice(tmp_path) -> None:
    fields = make_invoice(vendor="Northwind Traders", document_number="INV-2024-0042")
    text = render_text(fields, "labeled", "iso")
    png_path = tmp_path / "invoice.png"
    render_png(text.splitlines(), png_path)
    result = extract_document(png_path)
    assert result.text_method == "tesseract"
    assert result.document.vendor == "Northwind Traders"
    assert result.document.document_number == "INV-2024-0042"
    assert result.validation_ok is True


def test_skip_marker_matches_the_binary() -> None:
    # Documents the contract: when the binary is absent this file's OCR test is skipped.
    assert tesseract_available() is (shutil.which("tesseract") is not None)
