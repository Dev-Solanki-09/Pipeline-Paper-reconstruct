"""Tests for S5b Hindi stage (Devanagari normalization & bilingual column separation)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Lang,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.stages.base import StageContext
from examforge.stages.s5_hindi import (
    S5Hindi,
    contains_devanagari,
    normalize_hindi_text,
    split_bilingual_text,
)


class TestHindiNormalization:
    def test_contains_devanagari(self):
        assert contains_devanagari("बल का मात्रक न्यूटन है")
        assert not contains_devanagari("Unit of force is Newton")

    def test_danda_replacement(self):
        raw = "यह एक परीक्षण वाक्य है |"
        norm = normalize_hindi_text(raw)
        assert "।" in norm
        assert "|" not in norm

    def test_double_danda_replacement(self):
        raw = "प्रथम अध्याय समाप्त ||"
        norm = normalize_hindi_text(raw)
        assert "॥" in norm

    def test_math_pipes_not_altered(self):
        # A formula with pipes not preceded by Devanagari
        raw = "|x| = 5"
        norm = normalize_hindi_text(raw)
        assert norm == "|x| = 5"


class TestBilingualSeparation:
    def test_multiline_separation(self):
        text = "Find the force acting on the particle.\nकण पर लगने वाले बल की गणना कीजिए।"
        en, hi = split_bilingual_text(text)
        assert en == "Find the force acting on the particle."
        assert hi == "कण पर लगने वाले बल की गणना कीजिए।"

    def test_slash_separated_option(self):
        text = "10 m/s / 10 मी/से"
        en, hi = split_bilingual_text(text)
        assert en == "10 m/s"
        assert hi == "10 मी/से"


class TestS5HindiStage:
    def test_precondition_requires_blocks(self, empty_document, tmp_path):
        ctx = StageContext(
            document=empty_document,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s5b",
            run_dir=tmp_path,
        )
        stage = S5Hindi()
        violations = stage.validate_preconditions(ctx)
        assert len(violations) > 0

    def test_stage_separates_bilingual_question(self, tmp_path):
        b1 = Block(
            id="b1",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=50, x2=400, y2=80),
            order=0,
            lang=Lang.MIXED,
            text="Calculate momentum.\nसंवेग की गणना करें |",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )

        q1 = Question(
            id="q1",
            number=1,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Calculate momentum.\nसंवेग की गणना करें |",
            options=[
                Option(
                    label="A",
                    text_str_en="5 kg m/s / 5 किग्रा मी/से",
                )
            ],
            source_pages=[1],
        )

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Physics"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            blocks=[b1],
            questions=[q1],
        )

        ctx = StageContext(
            document=doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s5b",
            run_dir=tmp_path,
        )
        stage = S5Hindi()
        result = stage.run(ctx)

        assert q1.stem_text_en == "Calculate momentum."
        assert "संवेग की गणना करें" in q1.stem_text_hi
        assert "।" in q1.stem_text_hi  # pipe replaced
        assert q1.options[0].text_str_en == "5 kg m/s"
        assert "5 किग्रा मी/से" in q1.options[0].text_str_hi
        assert result.metrics["bilingual_split_count"] >= 2
        post_violations = stage.validate_postconditions(result)
        assert len(post_violations) == 0
