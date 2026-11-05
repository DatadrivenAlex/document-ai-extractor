import json
from collections import Counter

from document_ai.generator import generate_corpus
from document_ai.models import ValidatedDocument


def test_corpus_is_seed_stable(tmp_path) -> None:
    first = generate_corpus(11, 4, tmp_path / "a")
    second = generate_corpus(11, 4, tmp_path / "b")
    other = generate_corpus(12, 4, tmp_path / "c")
    assert [doc.text for doc in first] == [doc.text for doc in second]
    assert [doc.fields.model_dump() for doc in first] == [doc.fields.model_dump() for doc in second]
    assert [doc.text for doc in first] != [doc.text for doc in other]


def test_writes_pdf_png_and_json(tmp_path) -> None:
    document = generate_corpus(1, 1, tmp_path)[0]
    assert document.pdf_path.read_bytes().startswith(b"%PDF")
    assert document.png_path.read_bytes().startswith(b"\x89PNG")
    payload = json.loads(document.json_path.read_text(encoding="utf-8"))
    restored = ValidatedDocument.model_validate(payload["fields"])
    assert restored == document.fields
    assert payload["layout"] == "labeled"
    assert payload["id"] == "invoice_001"


def test_layouts_are_balanced_and_cover_both_document_types(tmp_path) -> None:
    documents = generate_corpus(42, 8, tmp_path)
    assert Counter(doc.layout for doc in documents) == {
        "labeled": 2,
        "prose": 2,
        "receipt": 2,
        "table": 2,
    }
    assert {doc.fields.document_type for doc in documents} == {"invoice", "receipt"}
    assert all(doc.fields.line_items for doc in documents)
    assert all(item.quantity > 0 for doc in documents for item in doc.fields.line_items)


def test_receipts_have_no_due_date_and_invoices_do(tmp_path) -> None:
    documents = generate_corpus(5, 4, tmp_path)
    for document in documents:
        if document.fields.document_type == "receipt":
            assert document.fields.due_date is None
        else:
            assert document.fields.due_date is not None
            assert document.fields.due_date >= document.fields.issue_date
