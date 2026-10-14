"""Tests for S4 Structure stage (question segmentation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    ExamMetadata,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.stages.base import StageContext
from examforge.stages.s3_parse import S3Parse
from examforge.stages.s4_structure import (
    PATTERN_DOT,
    PATTERN_Q_DOT,
    S4Structure,
    _check_numbering_continuity,
    _detect_question_kind,
    _find_question_pattern,
    _parse_options,
)


class TestFindQuestionPattern:
    def test_detects_dot_pattern(self):
        text = "1. stem\n2. stem\n3. stem\n4. stem\n5. stem"
        pattern = _find_question_pattern(text)
        assert pattern is not None
        assert pattern == PATTERN_DOT

    def test_detects_q_dot_pattern(self):
        text = "Q.1 stem\nQ.2 stem\nQ.3 stem\nQ.4 stem\nQ.5 stem"
        pattern = _find_question_pattern(text)
        assert pattern is not None
        assert pattern == PATTERN_Q_DOT

    def test_returns_none_for_no_pattern(self):
        text = "Random text with no question numbers whatsoever."
        assert _find_question_pattern(text) is None


class TestParseOptions:
    def test_four_options(self):
        blocks = [
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=0, y1=0, x2=10, y2=10),
                text="What is X?\n(A) first\n(B) second\n(C) third\n(D) fourth",
            )
        ]
        stem_blocks, options = _parse_options(blocks)
        assert len(options) == 4
        assert [o.label for o in options] == ["A", "B", "C", "D"]
        assert options[0].text_str_en == "first"
        assert options[1].text_str_en == "second"
        assert options[2].text_str_en == "third"
        assert options[3].text_str_en == "fourth"

    def test_stem_before_options(self):
        blocks = [
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=0, y1=0, x2=10, y2=10),
                text="This is the stem text.\n(A) opt1\n(B) opt2",
            )
        ]
        _, options = _parse_options(blocks)
        assert len(options) == 2

    def test_no_options(self):
        blocks = [
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=0, y1=0, x2=10, y2=10),
                text="Calculate the integral of x^2 dx from 0 to 1.",
            )
        ]
        _, options = _parse_options(blocks)
        assert len(options) == 0


class TestDetectQuestionKind:
    def test_mcq_single_default(self):
        options = [Option(label="A"), Option(label="B"), Option(label="C"), Option(label="D")]
        assert _detect_question_kind("A simple question", options) == QuestionKind.MCQ_SINGLE

    def test_mcq_multi(self):
        options = [Option(label="A"), Option(label="B"), Option(label="C"), Option(label="D")]
        assert _detect_question_kind("This question has more than one correct option.", options) == QuestionKind.MCQ_MULTI

    def test_numeric(self):
        assert _detect_question_kind("Find the numerical value of the answer.", []) == QuestionKind.NUMERIC


class TestNumberingContinuity:
    def test_continuous(self):
        questions = [
            Question(id=f"q{i}", number=i, stem_text_en=f"Q{i}")
            for i in range(1, 6)
        ]
        issues = _check_numbering_continuity(questions)
        assert len(issues) == 0

    def test_gap(self):
        questions = [
            Question(id=f"q{i}", number=i, stem_text_en=f"Q{i}")
            for i in [1, 2, 4, 5]
        ]
        issues = _check_numbering_continuity(questions)
        assert len(issues) == 1
        assert "Question 3 not found" in issues[0].message

    def test_duplicate(self):
        questions = [
            Question(id="q1", number=1, stem_text_en="Q1"),
            Question(id="q2a", number=2, stem_text_en="Q2"),
            Question(id="q2b", number=2, stem_text_en="Q2 dup"),
            Question(id="q3", number=3, stem_text_en="Q3"),
        ]
        issues = _check_numbering_continuity(questions)
        assert any("Duplicate question number 2" in iss.message for iss in issues)


class TestS4StructureStage:
    def test_preconditions_fail_without_blocks(self, empty_document, tmp_path):
        ctx = StageContext(
            document=empty_document,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s4",
            run_dir=tmp_path,
        )
        stage = S4Structure()
        violations = stage.validate_preconditions(ctx)
        assert len(violations) > 0

    def test_end_to_end(self, sample_pdf_path, tmp_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")

        # Create exam document with pages 4, 5, 6
        exam_doc = ExamDocument(
            source_path=str(sample_pdf_path),
            source_hash="sample_hash",
            metadata=ExamMetadata(exam_name="JEE Adv"),
            pages=[
                PageInfo(
                    page_number=4,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.QUESTIONS,
                    width_px=594,
                    height_px=841,
                ),
                PageInfo(
                    page_number=5,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.QUESTIONS,
                    width_px=594,
                    height_px=841,
                ),
                PageInfo(
                    page_number=6,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.QUESTIONS,
                    width_px=594,
                    height_px=841,
                ),
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s4",
            run_dir=tmp_path,
        )

        s3 = S3Parse()
        s3_res = s3.run(ctx)
        assert len(s3_res.document.blocks) > 0

        s4 = S4Structure()
        s4_res = s4.run(ctx)

        assert len(s4_res.document.questions) >= 3
        for q in s4_res.document.questions:
            assert len(q.source_pages) > 0
            assert q.number > 0
            assert len(q.stem_text_en) > 0

    def test_rollback_flag_off_restores_v1_logic(self, tmp_path):
        from examforge.config import ExamForgeConfig
        cfg = ExamForgeConfig()
        cfg.flags["layout_v2"] = False

        blocks = [
            Block(id="b1", page=1, bbox=BBox(x1=50, y1=50, x2=550, y2=100), text="1. Question one?\n(A) yes\n(B) no"),
            Block(id="b2", page=1, bbox=BBox(x1=50, y1=120, x2=550, y2=180), text="2. Question two?\n(A) true\n(B) false"),
        ]
        doc = ExamDocument(
            schema_version=2,
            source_path="test.pdf",
            metadata=ExamMetadata(title="Test Rollback"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS, width_px=600, height_px=800)],
            blocks=blocks,
        )
        ctx = StageContext(
            document=doc,
            config=cfg,
            spec=None,
            stage_dir=tmp_path / "s4",
            run_dir=tmp_path,
        )
        s4 = S4Structure()
        res = s4.run(ctx)
        assert len(res.document.questions) == 2
        assert res.document.questions[0].number == 1
        assert res.document.questions[1].number == 2
