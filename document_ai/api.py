"""HTTP API: upload a PDF or image and receive extracted JSON."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from document_ai import __version__
from document_ai.errors import (
    LLMProviderError,
    TesseractNotAvailableError,
    UnsupportedFileTypeError,
)
from document_ai.llm import build_provider
from document_ai.models import ExtractionResult
from document_ai.pipeline import extract_document
from document_ai.text import IMAGE_SUFFIXES, tesseract_available

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}

app = FastAPI(
    title="Document AI Extractor",
    version=__version__,
    summary="Extract invoice and receipt fields from a PDF or image.",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "docs": "/docs",
        "extract": "POST /v1/extract",
        "health": "/health",
        "name": "document-ai-extractor",
        "version": __version__,
    }


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "tesseract": tesseract_available(), "version": __version__}


@app.post("/v1/extract", response_model=ExtractionResult)
async def extract_endpoint(
    file: UploadFile = File(...),
    llm: str = Query(default="none", pattern="^(none|mock|openai)$"),
) -> ExtractionResult:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type '{suffix or 'unknown'}'. Upload a PDF or an image.",
        )
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(payload) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the 10 MB limit")
    try:
        provider = build_provider(llm)
    except LLMProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    descriptor, name = tempfile.mkstemp(suffix=suffix)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_bytes(payload)
        return extract_document(temporary, llm=provider)
    except TesseractNotAvailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)
