import json

import pytest

from document_ai.cli import main
from document_ai.generator import generate_corpus


def test_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0


def test_generate_and_extract(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "docs"
    assert main(["generate", "--seed", "3", "--count", "1", "--out", str(out)]) == 0
    capsys.readouterr()
    pdf = out / "invoice_001.pdf"
    assert pdf.is_file()
    assert (out / "invoice_001.png").is_file()
    assert (out / "invoice_001.json").is_file()
    assert main(["extract", str(pdf), "--no-raw-text"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["validation_ok"] is True
    assert payload["raw_text"] is None
    assert payload["document"]["document_type"] == "invoice"


def test_evaluate_writes_a_report(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = tmp_path / "nested" / "report.json"
    code = main(["evaluate", "--seed", "2", "--count", "4", "--out", str(report_path)])
    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["seed"] == 2
    assert report["count"] == 4
    captured = capsys.readouterr()
    assert "Rules only" in captured.out
    assert str(report_path) in captured.out


def test_openai_without_a_key_returns_nonzero(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    document = generate_corpus(1, 1, tmp_path)[0]
    assert main(["extract", str(document.pdf_path), "--llm", "openai"]) == 1
