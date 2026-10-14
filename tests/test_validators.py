"""Tests for spec rule validators and S8 Verify stage."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    IssueSeverity,
    Lang,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
    WatermarkTier,
)
from examforge.spec import Rule, RuleSeverity, Spec
from examforge.stages.base import StageContext
from examforge.stages.s8_verify import S8Verify
from examforge.validators.r01_no_furniture import validate_no_furniture
from examforge.validators.r02_no_branding import validate_no_branding
from examforge.validators.r03_no_watermark import validate_watermark_residual
from examforge.validators.r04_continuous import validate_continuous_flow
from examforge.validators.r05_bilingual import validate_bilingual_pairs
from examforge.validators.r06_complete import validate_numbering_continuity
from examforge.validators.r07_formulas import validate_formula_roundtrip
from examforge.validators.r08_figures import validate_figures_present
from examforge.validators.r09_unicode import validate_devanagari_unicode


def _make_block(
    block_id: str,
    text: str,
    block_type: BlockType = BlockType.TEXT,
    status: BlockStatus = BlockStatus.TRUSTED,
    lang: Lang = Lang.EN,
) -> Block:
    return Block(
        id=block_id,
        page=1,
        type=block_type,
        bbox=BBox(x1=10, y1=10, x2=100, y2=20),
        order=0,
        text=text,
        confidence=1.0,
        status=status,
        lang=lang,
    )


class TestIndividualValidators:
    def test_r01_no_furniture(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="no_headers_footers_page_numbers")
        b1 = _make_block("b1", "FOOTER TEXT", block_type=BlockType.FOOTER)
        b2 = _make_block("b2", "FOOTER TEXT", block_type=BlockType.FOOTER, status=BlockStatus.DROPPED)
        b3 = _make_block("b3", "SPACE FOR ROUGH WORK")

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b1, b2, b3],
        )

        issues = validate_no_furniture(doc, rule)
        assert len(issues) == 2
        element_ids = [i.element_id for i in issues]
        assert "b1" in element_ids
        assert "b3" in element_ids

    def test_r02_no_branding(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="no_brand_text_or_logo")
        b1 = _make_block("b1", "Visit https://allen.ac.in for answer key")
        b2 = _make_block("b2", "A body moves with uniform velocity")

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b1, b2],
        )

        issues = validate_no_branding(doc, rule)
        assert len(issues) == 1
        assert issues[0].element_id == "b1"

    def test_r03_no_watermark(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="watermark_residual")
        p1 = PageInfo(page_number=1, watermark_tier=WatermarkTier.W5_BAKED)

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[p1],
        )

        issues = validate_watermark_residual(doc, rule)
        assert len(issues) == 1
        assert issues[0].page == 1

    def test_r04_continuous_flow(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="no_page_wrappers_or_breaks")
        doc_empty = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            questions=[],
        )

        issues = validate_continuous_flow(doc_empty, rule)
        assert len(issues) == 1

    def test_r05_bilingual_pairs(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="en_hi_pairs_complete")
        b_hi = _make_block("b_hi", "हिंदी पाठ", lang=Lang.HI)
        q1 = Question(
            id="q1",
            number=1,
            stem_text_en="Find acceleration",
            stem_text_hi="",  # Missing Hindi stem!
        )

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b_hi],
            questions=[q1],
        )

        issues = validate_bilingual_pairs(doc, rule)
        assert len(issues) == 1
        assert "Hindi" in issues[0].message

    def test_r06_continuity(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="numbering_continuity")
        q1 = Question(id="q1", number=1, stem_text_en="Q1")
        q3 = Question(id="q3", number=3, stem_text_en="Q3")  # Gap at 2

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            questions=[q1, q3],
        )

        issues = validate_numbering_continuity(doc, rule)
        assert len(issues) == 1
        assert "Missing question number 2" in issues[0].message

    def test_r07_formulas(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="formula_roundtrip")
        b_bad = _make_block("b_bad", "$E = mc^2", block_type=BlockType.FORMULA)  # Unbalanced single dollar

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b_bad],
        )

        issues = validate_formula_roundtrip(doc, rule)
        assert len(issues) == 1
        assert "Unbalanced $" in issues[0].message

    def test_r08_figures(self):
        rule = Rule(severity=RuleSeverity.BLOCKER, check="figure_clean_border_and_present")
        q_ref = Question(
            id="q1",
            number=1,
            stem_text_en="As shown in the circuit diagram below, find current.",
            figure_refs=[],  # Missing figure ref!
        )

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            questions=[q_ref],
        )

        issues = validate_figures_present(doc, rule)
        assert len(issues) == 1
        assert "references a figure" in issues[0].message

    def test_r09_unicode(self):
        rule = Rule(severity=RuleSeverity.WARN, check="devanagari_nfc_and_lexicon")
        # NFD form of U+0929 (NNNA) is U+0928 (NA) + U+093C (NUKTA)
        decomposed_text = "\u0928\u093c"
        b_nfd = _make_block("b1", decomposed_text, lang=Lang.HI)

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b_nfd],
        )

        issues = validate_devanagari_unicode(doc, rule)
        assert len(issues) == 1
        assert "NFC" in issues[0].message


class TestS8VerifyStage:
    def test_end_to_end_verification(self, tmp_path):
        q1 = Question(
            id="q1",
            number=1,
            kind=QuestionKind.MCQ_SINGLE,
            stem_text_en="Find the maximum speed of the moving block.",
            options=[
                Option(label="A", text_str_en="Option A"),
                Option(label="B", text_str_en="Option B"),
            ],
        )
        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            questions=[q1],
        )

        ctx = StageContext(
            document=doc,
            config=None,
            spec=Spec.default(),
            stage_dir=tmp_path / "s8",
            run_dir=tmp_path,
        )
        stage = S8Verify()
        result = stage.run(ctx)

        assert result.metrics["rules_evaluated"] > 0
        assert result.metrics["validators_matched"] > 0
        assert result.metrics["blockers"] == 0
