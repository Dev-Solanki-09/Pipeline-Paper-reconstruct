"""Tests for S6 Figures stage (figure extraction and question assignment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureClass,
    PageClassification,
    PageInfo,
    Question,
)
from examforge.stages.base import StageContext
from examforge.stages.s3_parse import S3Parse
from examforge.stages.s4_structure import S4Structure
from examforge.stages.s6_figures import (
    S6Figures,
    _assign_figures_to_questions,
    _classify_figure,
)


class TestClassifyFigure:
    def test_skip_tiny_images(self):
        """Images smaller than 50x50 should return None."""
        assert _classify_figure(30, 40) is None
        assert _classify_figure(49, 100) is None
        assert _classify_figure(100, 49) is None

    def test_skip_decorative_lines(self):
        """Very wide or very tall images (aspect > 5:1) should return None."""
        assert _classify_figure(500, 50) is None
        assert _classify_figure(50, 500) is None

    def test_normal_diagram(self):
        """300x200 image -> FigureClass.DIAGRAM."""
        assert _classify_figure(300, 200) == FigureClass.DIAGRAM
        assert _classify_figure(100, 100) == FigureClass.DIAGRAM


class TestAssignFiguresToQuestions:
    def test_figure_assigned_to_nearest_question(self):
        """Figure on page 5 at y=400 should be assigned to the question spanning that y coordinate."""
        q1 = Question(
            id="q1",
            number=1,
            stem_en=[Block(id="b1", page=5, bbox=BBox(x1=50, y1=100, x2=500, y2=250), text="Q1")],
            source_pages=[5],
        )
        q2 = Question(
            id="q2",
            number=2,
            stem_en=[Block(id="b2", page=5, bbox=BBox(x1=50, y1=300, x2=500, y2=550), text="Q2")],
            source_pages=[5],
        )

        fig = Figure(
            id="fig_5_1",
            page=5,
            bbox=BBox(x1=100, y1=400, x2=300, y2=500),
            classification=FigureClass.DIAGRAM,
        )

        _assign_figures_to_questions([fig], [q1, q2])

        assert fig.question_ref == "q2"
        assert "fig_5_1" in q2.figure_refs
        assert "fig_5_1" not in q1.figure_refs

    def test_figure_on_different_page(self):
        """A figure on page 3 should not be assigned to a question on page 5."""
        q = Question(
            id="q1",
            number=1,
            stem_en=[Block(id="b1", page=5, bbox=BBox(x1=50, y1=100, x2=500, y2=250), text="Q1")],
            source_pages=[5],
        )
        fig = Figure(
            id="fig_3_1",
            page=3,
            bbox=BBox(x1=100, y1=100, x2=200, y2=200),
            classification=FigureClass.DIAGRAM,
        )

        _assign_figures_to_questions([fig], [q])
        assert fig.question_ref is None
        assert len(q.figure_refs) == 0


class TestS6FiguresStage:
    def test_end_to_end(self, sample_pdf_path, tmp_path):
        """Run S3 + S4 + S6 on pages 4 and 5 of JEE PDF -> diagrams extracted and assigned."""
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")

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
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s6",
            run_dir=tmp_path,
        )

        # Parse text and structure
        S3Parse().run(ctx)
        S4Structure().run(ctx)

        # Run figures stage
        s6 = S6Figures()
        result = s6.run(ctx)

        assert len(result.document.figures) > 0
        assert result.metrics["figures_extracted"] > 0

        # Check postconditions pass
        violations = s6.validate_postconditions(result)
        assert len(violations) == 0
