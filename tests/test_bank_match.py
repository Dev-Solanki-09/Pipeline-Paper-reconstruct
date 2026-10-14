"""Tests for Question Bank Strict Matcher (Phase 12.3)."""

from __future__ import annotations

import json
from pathlib import Path

from examforge.bank.fingerprint import compute_number_signature, compute_simhash_64
from examforge.bank.match import MatchKind, QuestionBankMatcher
from examforge.bank.store import BankQuestionRecord, QuestionBankStore
from examforge.ir.schema import Option, Question


def test_exact_reuse_match(tmp_path: Path):
    store = QuestionBankStore(tmp_path / "bank.db")
    matcher = QuestionBankMatcher(store)

    q = Question(
        id="q1",
        number=1,
        stem_text_en="A 5 kg block moves at 10 m/s on a frictionless surface.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )
    sig = compute_number_signature(q)
    sh = compute_simhash_64(q.stem_text_en)

    record = BankQuestionRecord(
        content_hash="q1_hash",
        simhash=sh,
        number_signature=sig,
        languages=["en"],
        ir_json=json.dumps(q.model_dump(mode="json")),
        verified_by="human",
        source_paper="test.pdf",
        exam_family="neet_ug",
    )
    store.insert_question(record)

    res = matcher.match(q, exam_family="neet_ug")
    assert res.kind == MatchKind.EXACT_REUSE
    assert res.matched_record is not None
    assert res.matched_record.content_hash == "q1_hash"


def test_digit_change_strictly_blocks_exact_reuse(tmp_path: Path):
    store = QuestionBankStore(tmp_path / "bank.db")
    matcher = QuestionBankMatcher(store)

    original_q = Question(
        id="q1",
        number=1,
        stem_text_en="A 5 kg block moves at 10 m/s on a frictionless surface.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )
    sig = compute_number_signature(original_q)
    sh = compute_simhash_64(original_q.stem_text_en)

    store.insert_question(
        BankQuestionRecord(
            content_hash="q1_hash",
            simhash=sh,
            number_signature=sig,
            languages=["en"],
            ir_json=json.dumps(original_q.model_dump(mode="json")),
            verified_by="human",
            source_paper="test.pdf",
            exam_family="neet_ug",
        )
    )

    # Mutated query: 5 kg changed to 6 kg
    mutated_q = Question(
        id="q2",
        number=2,
        stem_text_en="A 6 kg block moves at 10 m/s on a frictionless surface.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )

    res = matcher.match(mutated_q, exam_family="neet_ug")
    # Must NOT be EXACT_REUSE! Can only be NEAR_HINT or NO_MATCH
    assert res.kind != MatchKind.EXACT_REUSE
    assert res.kind in (MatchKind.NEAR_HINT, MatchKind.NO_MATCH)


def test_unit_change_strictly_blocks_exact_reuse(tmp_path: Path):
    store = QuestionBankStore(tmp_path / "bank.db")
    matcher = QuestionBankMatcher(store)

    original_q = Question(
        id="q1",
        number=1,
        stem_text_en="The electric potential is 10 V.",
        options=[Option(label="A", text_str_en="10 V")],
    )
    sig = compute_number_signature(original_q)
    sh = compute_simhash_64(original_q.stem_text_en)

    store.insert_question(
        BankQuestionRecord(
            content_hash="q1_hash",
            simhash=sh,
            number_signature=sig,
            languages=["en"],
            ir_json=json.dumps(original_q.model_dump(mode="json")),
            verified_by="human",
            source_paper="test.pdf",
            exam_family="neet_ug",
        )
    )

    # Mutated: 10 V -> 10 mV
    mutated_q = Question(
        id="q2",
        number=2,
        stem_text_en="The electric potential is 10 mV.",
        options=[Option(label="A", text_str_en="10 mV")],
    )

    res = matcher.match(mutated_q, exam_family="neet_ug")
    assert res.kind != MatchKind.EXACT_REUSE
