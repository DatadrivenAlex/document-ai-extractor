"""The published accuracy table has to match a fresh run of the same command."""

from __future__ import annotations

import json
from pathlib import Path

from document_ai.evaluate import render_markdown, run_evaluation

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "eval" / "baseline_report.json"


def test_committed_baseline_matches_a_fresh_run(tmp_path) -> None:
    fresh = run_evaluation(seed=42, count=40, dest_dir=tmp_path)
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert fresh == committed


def test_readme_includes_the_measured_table() -> None:
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert committed["markdown"] == render_markdown(committed)
    assert committed["markdown"] in readme
