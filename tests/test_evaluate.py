from document_ai.evaluate import render_markdown, run_evaluation


def test_small_eval_shows_the_mock_filling_prose(tmp_path) -> None:
    report = run_evaluation(seed=42, count=4, dest_dir=tmp_path)
    assert report["layout_counts"] == {"labeled": 1, "prose": 1, "receipt": 1, "table": 1}
    rules = report["modes"]["rules"]
    mock = report["modes"]["rules_plus_mock_llm"]
    assert rules["field_accuracy"]["vendor"] == {"accuracy": 0.75, "correct": 3, "total": 4}
    assert mock["field_accuracy"]["vendor"] == {"accuracy": 1.0, "correct": 4, "total": 4}
    assert mock["document_exact_match"]["correct"] == 4
    assert rules["document_exact_match"]["correct"] == 3
    assert "not a measurement on real vendor invoices" in report["notes"]
    assert render_markdown(report) == report["markdown"]
    assert "3/4 (75.0%)" in report["markdown"]
    assert "4/4 (100.0%)" in report["markdown"]
