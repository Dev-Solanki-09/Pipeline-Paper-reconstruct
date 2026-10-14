"""Tests for figure-to-question association (multi-signal scoring and constrained greedy assignment)."""

from __future__ import annotations

import pytest

from examforge.figures.associate import (
    associate_figures_to_questions,
    score_figure_question_match,
)
from examforge.ir.schema import (
    BBox,
    Block,
    Figure,
    FigureClass,
    Issue,
    IssueSeverity,
    Option,
    Question,
)


class TestFigureAssociation:
    def test_vertical_proximity_and_cue_boost(self):
        """Question with figure cue receives score boost and wins assignment."""
        q1 = Question(
            id="q1",
            number=1,
            stem_en=[Block(id="b1", page=2, bbox=BBox(x1=50, y1=100, x2=500, y2=180), text="What is the speed of sound?")],
            stem_text_en="What is the speed of sound?",
            source_pages=[2],
        )
        q2 = Question(
            id="q2",
            number=2,
            stem_en=[Block(id="b2", page=2, bbox=BBox(x1=50, y1=200, x2=500, y2=280), text="In the given figure, find the equivalent resistance.")],
            stem_text_en="In the given figure, find the equivalent resistance.",
            source_pages=[2],
        )

        fig = Figure(
            id="fig_2_1",
            page=2,
            bbox=BBox(x1=100, y1=300, x2=300, y2=450),
            classification=FigureClass.DIAGRAM,
        )

        score1 = score_figure_question_match(fig, q1)
        score2 = score_figure_question_match(fig, q2)

        # q2 has figure cue "given figure" and is physically closer
        assert score2 > score1

        issues = associate_figures_to_questions([fig], [q1, q2])
        assert fig.question_ref == "q2"
        assert "fig_2_1" in q2.figure_refs
        assert len(issues) == 0

    def test_hindi_figure_cue_boost(self):
        """Hindi cue 'दिए गए चित्र' boosts score."""
        q = Question(
            id="q1",
            number=1,
            stem_hi=[Block(id="b1", page=1, bbox=BBox(x1=50, y1=100, x2=500, y2=200), text="दिए गए चित्र में परिपथ का तुल्य प्रतिरोध ज्ञात कीजिए।")],
            stem_text_hi="दिए गए चित्र में परिपथ का तुल्य प्रतिरोध ज्ञात कीजिए।",
            source_pages=[1],
        )
        fig = Figure(
            id="fig_1_1",
            page=1,
            bbox=BBox(x1=100, y1=220, x2=300, y2=360),
            classification=FigureClass.DIAGRAM,
        )

        score = score_figure_question_match(fig, q)
        assert score >= 10.0  # high confidence match

    def test_option_figure_assignment(self):
        """Figures aligned inside option cells attach to option_ref."""
        opt_a = Option(
            label="A",
            text_en=[Block(id="oa", page=3, bbox=BBox(x1=50, y1=200, x2=250, y2=280), text="(A)")],
        )
        opt_b = Option(
            label="B",
            text_en=[Block(id="ob", page=3, bbox=BBox(x1=300, y1=200, x2=500, y2=280), text="(B)")],
        )

        q = Question(
            id="q1",
            number=1,
            stem_en=[Block(id="b1", page=3, bbox=BBox(x1=50, y1=100, x2=500, y2=180), text="Which circuit matches?")],
            stem_text_en="Which circuit matches?",
            options=[opt_a, opt_b],
            source_pages=[3],
        )

        fig_a = Figure(
            id="fig_3_a",
            page=3,
            bbox=BBox(x1=80, y1=210, x2=230, y2=270),
            scale_class="img-opt",
            classification=FigureClass.DIAGRAM,
        )

        associate_figures_to_questions([fig_a], [q])
        assert fig_a.question_ref == "q1"
        assert fig_a.option_ref == "A"
        assert opt_a.figure_ref == "fig_3_a"

    def test_unassigned_figure_emits_issue(self):
        """An ambiguous figure outside any question bounds emits an Issue."""
        q = Question(
            id="q1",
            number=1,
            stem_en=[Block(id="b1", page=5, bbox=BBox(x1=50, y1=100, x2=500, y2=200), text="Question 1")],
            source_pages=[5],
        )
        # Figure on page 7 (no questions on page 7)
        fig_orphan = Figure(
            id="fig_7_orphan",
            page=7,
            bbox=BBox(x1=100, y1=100, x2=300, y2=300),
            classification=FigureClass.DIAGRAM,
        )

        issues = associate_figures_to_questions(
            [fig_orphan],
            [q],
            allow_proportional_fallback=False,
        )
        assert fig_orphan.question_ref is None
        assert len(issues) == 1
        assert issues[0].stage == "s6_figures"
        assert "unassigned" in issues[0].message.lower()
