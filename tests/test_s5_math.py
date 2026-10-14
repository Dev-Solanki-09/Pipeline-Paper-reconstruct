"""Tests for S5 Math stage (Unicode math to LaTeX conversion)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.stages.base import StageContext
from examforge.stages.s5_math import (
    S5Math,
    check_balanced_delimiters,
    convert_unicode_math,
    format_math,
    wrap_math_delimiters,
)


class TestConvertUnicodeMath:
    def test_superscripts(self):
        assert convert_unicode_math("x² + y³ = r²") == "x^{2} + y^{3} = r^{2}"

    def test_subscripts(self):
        assert convert_unicode_math("H₂SO₄") == "H_{2}SO_{4}"

    def test_greek_letters(self):
        assert convert_unicode_math("θ = 30°") == r"\theta = 30^{\circ}"
        assert convert_unicode_math("λ = 500 nm") == r"\lambda = 500 nm"

    def test_operators(self):
        assert convert_unicode_math("a ≤ b × c") == r"a \le b \times c"

    def test_square_roots(self):
        assert convert_unicode_math("√(2gh)") == r"\sqrt{2gh}"
        assert convert_unicode_math("√2") == r"\sqrt{2}"


class TestWrapMathDelimiters:
    def test_pure_math_wrapped(self):
        res = wrap_math_delimiters(r"\theta = 30^{\circ}")
        assert res.startswith("$") and res.endswith("$")

    def test_already_wrapped_not_doubled(self):
        res = wrap_math_delimiters(r"$\theta = 30^{\circ}$")
        assert res == r"$\theta = 30^{\circ}$"


class TestCheckBalancedDelimiters:
    def test_balanced(self):
        assert check_balanced_delimiters(r"Let $\theta = 30^{\circ}$ be an angle") is True

    def test_unbalanced_dollar(self):
        assert check_balanced_delimiters(r"Let $\theta = 30^{\circ} be an angle") is False

    def test_unbalanced_braces(self):
        assert check_balanced_delimiters(r"Let $\theta = 30^{circ}$ be an angle") is True
        assert check_balanced_delimiters(r"Let $\theta = 30^{circ") is False


class TestS5MathStage:
    def test_precondition_requires_blocks(self, empty_document, tmp_path):
        ctx = StageContext(
            document=empty_document,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s5",
            run_dir=tmp_path,
        )
        stage = S5Math()
        violations = stage.validate_preconditions(ctx)
        assert len(violations) > 0

    def test_converts_formulas_in_blocks_and_questions(self, tmp_path):
        b1 = Block(
            id="b1",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=50, x2=300, y2=80),
            text="Calculate the kinetic energy E = ½mv² of the particle.",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )

        q1 = Question(
            id="q1",
            number=1,
            kind=QuestionKind.MCQ_SINGLE,
            stem_en=[b1],
            stem_text_en="Calculate the kinetic energy E = ½mv² of the particle.",
            options=[
                Option(label="A", text_str_en="E = 10 J"),
                Option(label="B", text_str_en="E = 20 J"),
            ],
            source_pages=[1],
        )

        doc = ExamDocument(
            source_path=str(tmp_path / "dummy.pdf"),
            source_hash="test",
            metadata=ExamMetadata(exam_name="Test"),
            blocks=[b1],
            questions=[q1],
        )

        ctx = StageContext(
            document=doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s5",
            run_dir=tmp_path,
        )

        stage = S5Math()
        result = stage.run(ctx)

        assert result.metrics["formulas_converted"] > 0
        assert "^{2}" in result.document.questions[0].stem_text_en
