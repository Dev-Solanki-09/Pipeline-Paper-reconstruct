"""Tests for SQLite-backed Question Bank Store (Phase 12.1)."""

from __future__ import annotations

from pathlib import Path

from examforge.bank.store import BankQuestionRecord, QuestionBankStore


def test_bank_store_init_and_migration(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)

    # Verify tables created and user_version set
    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        ver = cursor.fetchone()[0]
        assert ver == 1

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "questions" in tables
        assert "figures" in tables


def test_bank_store_insert_and_get(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)

    record = BankQuestionRecord(
        content_hash="abc123hash",
        simhash=12345678901234,
        number_signature="343:C:m/s",
        languages=["en", "hi"],
        ir_json='{"id": "q1", "stem_text_en": "Sample question"}',
        verified_by="human_approver",
        source_paper="neet_2025.pdf",
        exam_family="neet_ug",
    )

    store.insert_question(record)

    fetched = store.get_by_content_hash("abc123hash")
    assert fetched is not None
    assert fetched.content_hash == "abc123hash"
    assert fetched.simhash == 12345678901234
    assert fetched.number_signature == "343:C:m/s"
    assert fetched.languages == ["en", "hi"]
    assert fetched.verified_by == "human_approver"
    assert fetched.exam_family == "neet_ug"


def test_bank_store_stats_and_purge(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)

    assert store.stats()["question_count"] == 0

    record = BankQuestionRecord(
        content_hash="hash1",
        simhash=100,
        number_signature="10:m",
        languages=["en"],
        ir_json='{"id": "q1"}',
        verified_by="auto",
        source_paper="test.pdf",
        exam_family="jee_main",
    )
    store.insert_question(record)
    assert store.stats()["question_count"] == 1

    store.purge()
    assert store.stats()["question_count"] == 0
