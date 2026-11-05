"""Command line interface for generation, extraction, evaluation, and the API."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from document_ai.errors import DocumentAIError
from document_ai.evaluate import run_evaluation
from document_ai.generator import generate_corpus
from document_ai.llm import build_provider
from document_ai.pipeline import extract_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document-ai",
        description="Extract structured fields from invoices and receipts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Write a seeded synthetic corpus")
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--count", type=int, default=8)
    generate.add_argument("--out", type=Path, required=True)

    extract = subparsers.add_parser("extract", help="Extract fields from one PDF or image")
    extract.add_argument("path", type=Path)
    extract.add_argument("--llm", default="none", choices=("none", "mock", "openai"))
    extract.add_argument(
        "--no-raw-text",
        action="store_true",
        help="Omit the plain text from the JSON output",
    )

    evaluate = subparsers.add_parser("evaluate", help="Score extraction against ground truth")
    evaluate.add_argument("--seed", type=int, default=42)
    evaluate.add_argument("--count", type=int, default=40)
    evaluate.add_argument("--out", type=Path, required=True)

    serve = subparsers.add_parser("serve", help="Run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    args = parser.parse_args(argv)
    handlers = {
        "evaluate": _evaluate,
        "extract": _extract,
        "generate": _generate,
        "serve": _serve,
    }
    try:
        return handlers[args.command](args)
    except (DocumentAIError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _generate(args: argparse.Namespace) -> int:
    documents = generate_corpus(seed=args.seed, count=args.count, dest_dir=args.out)
    print(f"wrote {len(documents)} documents to {args.out} (seed {args.seed})")
    return 0


def _extract(args: argparse.Namespace) -> int:
    result = extract_document(
        args.path,
        llm=build_provider(args.llm),
        include_raw_text=not args.no_raw_text,
    )
    print(result.model_dump_json(indent=2))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="document-ai-eval-") as directory:
        report = run_evaluation(seed=args.seed, count=args.count, dest_dir=Path(directory))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(report["markdown"])
    print(f"\nwrote {args.out}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "document_ai.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
