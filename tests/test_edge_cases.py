"""Edge cases and robustness test suite (Phase 9)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from examforge.config import ExamForgeConfig
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
from examforge.spec import Spec
from examforge.stages.base import StageContext
from examforge.stages.s4_structure import _detect_question_kind, _parse_options_from_raw
from examforge.stages.s5_hindi import normalize_hindi_text, split_bilingual_text
from examforge.stages.s5_math import format_math
from examforge.stages.s9_package import S9Package


class TestEdgeCases:
    def test_numeric_question_without_options(self):
        """Numeric response questions should be classified as NUMERIC without options."""
        stem = "Find the integer value of n such that the system is in equilibrium."
        kind = _detect_question_kind(stem, options=[])
        assert kind == QuestionKind.NUMERIC

    def test_hindi_matras_normalization(self):
        """Devanagari text with complex matras and anusvaras remains valid NFC."""
        raw = "प्रक्षेपण कोण का मान 45° है |"
        norm = normalize_hindi_text(raw)
        assert "।" in norm
        assert "प्रक्षेपण" in norm
        assert "|" not in norm

    def test_large_question_number(self):
        """Pipeline handles high question numbers (e.g. Q.120)."""
        q = Question(
            id="q120",
            number=120,
            kind=QuestionKind.NUMERIC,
            stem_text_en="Find the resistance in ohms.",
        )
        assert q.number == 120

    def test_html_contains_no_page_constraints(self, tmp_path):
        """HTML output should not constrain browser printing with @page size or margin overrides."""
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="Continuous Exam Paper", year=2026),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            questions=[
                Question(
                    id="q1",
                    number=1,
                    kind=QuestionKind.MCQ_SINGLE,
                    stem_text_en="English question text.",
                    stem_text_hi="हिंदी प्रश्न पाठ।",
                    options=[
                        Option(label="A", text_str_en="Option A", text_str_hi="विकल्प A"),
                        Option(label="B", text_str_en="Option B", text_str_hi="विकल्प B"),
                    ],
                )
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=Spec.default(),
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        stage.run(ctx)

        html_content = (tmp_path / "output.html").read_text(encoding="utf-8")

        # Must NOT contain restrictive print constraints
        assert "@page" not in html_content
        assert "size: A4" not in html_content

        # Must contain simple dual column 50/50 bilingual continuous structure
        assert "col-50" in html_content
        assert "col-en" in html_content
        assert "col-hi" in html_content
        assert "English question text." in html_content
        assert "हिंदी प्रश्न पाठ।" in html_content

    def test_math_with_fractions_and_symbols(self):
        """Mathematical formulas with multiple symbols convert properly."""
        raw = "If α + β = π/2 and sin²θ + cos²θ = 1"
        res = format_math(raw)
        assert r"\alpha" in res
        assert r"\beta" in res
        assert r"\pi" in res
        assert "^{2}" in res
