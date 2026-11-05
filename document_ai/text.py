"""Read plain text from a digital PDF or from an image via Tesseract."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from document_ai.errors import TesseractNotAvailableError, UnsupportedFileTypeError

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class TextExtraction:
    text: str
    method: str
    warnings: list[str]


def normalize_text(text: str) -> str:
    """Collapse whitespace while keeping the line breaks the rules anchor on."""
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in cleaned.split("\n"):
        line = line.replace("\u00a0", " ")
        lines.append(re.sub(r"[ \t]+", " ", line).strip())
    return "\n".join(lines).strip()


def extract_text(path: Path | str) -> TextExtraction:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(source)
    if suffix in IMAGE_SUFFIXES:
        return _extract_image(source)
    raise UnsupportedFileTypeError(
        f"unsupported file type '{suffix or '(none)'}'. Upload a PDF or a PNG, JPEG, or TIFF."
    )


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _extract_pdf(path: Path) -> TextExtraction:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = normalize_text("\n".join(pages))
    warnings: list[str] = []
    if not text:
        warnings.append("PDF has no embedded text. If this is a scan, upload a PNG and run OCR.")
    return TextExtraction(text=text, method="pdfplumber", warnings=warnings)


def _extract_image(path: Path) -> TextExtraction:
    if not tesseract_available():
        raise TesseractNotAvailableError(
            "Tesseract OCR is not installed, so image text cannot be read. "
            "Install the tesseract-ocr package, or upload a digital PDF instead."
        )
    import pytesseract
    from PIL import Image

    with Image.open(path) as image:
        raw = pytesseract.image_to_string(image)
    text = normalize_text(raw)
    warnings: list[str] = []
    if not text:
        warnings.append("OCR returned no text.")
    return TextExtraction(text=text, method="tesseract", warnings=warnings)
