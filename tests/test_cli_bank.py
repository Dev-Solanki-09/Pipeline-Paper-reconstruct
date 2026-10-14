"""Tests for Question Bank CLI subcommands (Phase 12.4)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from examforge.bank.store import BankQuestionRecord, QuestionBankStore
from examforge.cli import main


def test_cli_bank_stats_and_purge(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)
    store.insert_question(
        BankQuestionRecord(
            content_hash="h1",
            simhash=1,
            number_signature="opts:1|nums:1|units:",
            languages=["en"],
            ir_json='{"id": "q1"}',
            verified_by="admin",
            source_paper="p.pdf",
            exam_family="neet_ug",
        )
    )

    runner = CliRunner()
    res = runner.invoke(main, ["bank", "stats", "--db", str(db_path)])
    assert res.exit_code == 0
    assert "Verified questions: 1" in res.output

    # Purge with confirmation
    res_purge = runner.invoke(main, ["bank", "purge", "--db", str(db_path)], input="y\n")
    assert res_purge.exit_code == 0
    assert "Purged all records" in res_purge.output

    res_after = runner.invoke(main, ["bank", "stats", "--db", str(db_path)])
    assert "Verified questions: 0" in res_after.output


def test_cli_bank_export_and_import(tmp_path: Path):
    db_path = tmp_path / "bank.db"
    store = QuestionBankStore(db_path)
    store.insert_question(
        BankQuestionRecord(
            content_hash="h2",
            simhash=2,
            number_signature="opts:2|nums:2|units:",
            languages=["en"],
            ir_json='{"id": "q2"}',
            verified_by="admin",
            source_paper="p.pdf",
            exam_family="jee_main",
        )
    )

    export_file = tmp_path / "bank.jsonl"
    runner = CliRunner()
    res_exp = runner.invoke(main, ["bank", "export", str(export_file), "--db", str(db_path)])
    assert res_exp.exit_code == 0
    assert "Exported 1 record(s)" in res_exp.output

    new_db = tmp_path / "new.db"
    res_imp = runner.invoke(main, ["bank", "import", str(export_file), "--db", str(new_db)])
    assert res_imp.exit_code == 0
    assert "Imported 1 record(s)" in res_imp.output
