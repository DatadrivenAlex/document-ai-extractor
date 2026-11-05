FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY document_ai ./document_ai

RUN pip install . \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

LABEL org.opencontainers.image.title="document-ai-extractor" \
      org.opencontainers.image.licenses="MIT"

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "document_ai.api:app", "--host", "0.0.0.0", "--port", "8000"]
