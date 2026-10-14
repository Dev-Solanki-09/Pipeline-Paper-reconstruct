"""Tests for ExamForge v2 Strict Invariants System (Phase 2)."""

from __future__ import annotations

import pytest

from examforge.ir.invariants import (
    InvariantError,
    assert_invariants,
    validate_invariants,
)
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    ExamMetadata,
    Figure,
    Marks,
    Option,
    PageInfo,
    Question,
)


def test_invariants_valid_document():
    doc = ExamDocument(
        source_path="sample.pdf",
        source_hash="sha256_mock",
        metadata=ExamMetadata(exam_name="NEET 2024"),
        pages=[PageInfo(page_number=1, width_px=1000, height_px=1400)],
        blocks=[
            Block(id="b1_0", page=1, bbox=BBox(x1=10, y1=10, x2=200, y2=50), text="Q1 stem"),
            Block(id="b1_1", page=1, bbox=BBox(x1=10, y1=60, x2=200, y2=100), text="Option 1"),
        ],
        figures=[Figure(id="fig_1", page=1, bbox=BBox(x1=20, y1=150, x2=120, y2=250))],
        questions=[
            Question(
                id="q_1",
                number=1,
                sequence_index=1,
                stem_text_en="What is the speed of light?",
                stem_en=[Block(id="b1_0", page=1, bbox=BBox(x1=10, y1=10, x2=200, y2=50))],
                options=[
                    Option(label="1", text_str_en="3e8 m/s"),
                    Option(label="2", text_str_en="2e8 m/s"),
                ],
                figure_refs=["fig_1"],
            )
        ],
    )

    violations = validate_invariants(doc)
    assert len(violations) == 0
    # assert_invariants should not raise
    assert_invariants(doc)


def test_invariants_detects_duplicate_block_ids():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        blocks=[
            Block(id="b1_dup", page=1, bbox=BBox(x1=0, y1=0, x2=10, y2=10)),
            Block(id="b1_dup", page=1, bbox=BBox(x1=10, y1=10, x2=20, y2=20)),
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-02" for v in violations)


def test_invariants_detects_duplicate_question_ids():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        questions=[
            Question(id="q_dup", number=1, sequence_index=1),
            Question(id="q_dup", number=2, sequence_index=2),
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-02" for v in violations)


def test_invariants_detects_invalid_bbox():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        blocks=[
            Block(id="b1_0", page=1, bbox=BBox(x1=100, y1=50, x2=50, y2=100)),  # x1 > x2!
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-03" for v in violations)


def test_invariants_detects_missing_figure_referent():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        questions=[
            Question(
                id="q_1",
                number=1,
                sequence_index=1,
                figure_refs=["nonexistent_fig"],
            )
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-06" for v in violations)

    with pytest.raises(InvariantError):
        assert_invariants(doc)


def test_invariants_detects_non_monotone_question_numbers():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        questions=[
            Question(id="q_1", number=10, section="Physics"),
            Question(id="q_2", number=5, section="Physics"),  # Out of order!
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-04" for v in violations)


def test_invariants_detects_choice_group_mark_mismatch():
    doc = ExamDocument(
        source_path="sample.pdf",
        pages=[PageInfo(page_number=1)],
        questions=[
            Question(
                id="q_1a",
                number=1,
                choice_group="or_group_1",
                marks=Marks(positive=5.0, negative=0.0),
            ),
            Question(
                id="q_1b",
                number=2,
                choice_group="or_group_1",
                marks=Marks(positive=3.0, negative=0.0),  # Mismatched marks!
            ),
        ],
    )
    violations = validate_invariants(doc)
    assert any(v.code == "INV-07" for v in violations)
