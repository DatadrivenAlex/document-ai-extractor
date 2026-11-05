PYTHON ?= python3

.PHONY: install test lint format eval generate serve docker-build ci

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

eval:
	$(PYTHON) -m document_ai evaluate --seed 42 --count 40 --out eval/baseline_report.json

generate:
	$(PYTHON) -m document_ai generate --seed 42 --count 8 --out data/samples

serve:
	$(PYTHON) -m uvicorn document_ai.api:app --host 127.0.0.1 --port 8000

docker-build:
	docker build -t document-ai-extractor .

ci: lint test
