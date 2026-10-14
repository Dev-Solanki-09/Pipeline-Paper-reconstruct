"""Tests for Question Bank Ingestion, Export, and Import (Phase 12.4)."""

from __future__ import annotations

from pathlib import Path

from examforge.bank.ingest import ingest_document
from examforge.bank.store import QuestionBankStore
from examforge.ir.schema import ExamDocument, Option, PageInfo, Question


def test_ingest_document_into_bank(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)

    doc = ExamDocument(
        source_path="test_exam.pdf",
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="What is force?",
                options=[
                    Option(label="A", text_str_en="m * a"),
                    Option(label="B", text_str_en="m * v"),
                ],
            ),
            Question(
                id="q2",
                number=2,
                stem_text_en="What is momentum?",
                options=[
                    Option(label="A", text_str_en="m * v"),
                    Option(label="B", text_str_en="m * a"),
                ],
            ),
        ],
    )

    count = ingest_document(
        store=store,
        doc=doc,
        verified_by="verifier_admin",
        exam_family="jee_main",
    )
    assert count == 2
    assert store.stats()["question_count"] == 2


def test_export_and_import_jsonl(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)

    doc = ExamDocument(
        source_path="test_exam.pdf",
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="What is power?",
                options=[Option(label="A", text_str_en="Work / time")],
            ),
        ],
    )
    ingest_document(store, doc, "admin", "neet_ug")

    export_path = tmp_path / "exported_bank.jsonl"
    exported_count = store.export_jsonl(export_path)
    assert exported_count == 1
    assert export_path.exists()

    # Create new store and import
    new_db = tmp_path / "new_bank.db"
    new_store = QuestionBankStore(new_db)
    imported_count = new_store.import_jsonl(export_path)
    assert imported_count == 1
    assert new_store.stats()["question_count"] == 1
