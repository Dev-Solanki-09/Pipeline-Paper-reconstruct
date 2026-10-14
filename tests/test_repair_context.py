"""Tests for minimal repair context builder."""

from __future__ import annotations

from examforge.ir.schema import Issue, IssueSeverity, Option, Question, QuestionKind
from examforge.repair.context import build_repair_context


class TestRepairContext:
    def test_build_compact_question_slice(self):
        q = Question(
            id="q_1",
            number=1,
            kind=QuestionKind.SINGLE_CORRECT,
            stem_text_en="What is the speed of light in vacuum?",
            options=[
                Option(label="A", text_str_en="3 x 10^8 m/s"),
                Option(label="B", text_str_en="3 x 10^6 m/s"),
            ],
            source_pages=[1],
        )
        issue = Issue(
            id="r11_q1_text_layer",
            stage="s8_verify",
            rule="text_layer_agreement",
            severity=IssueSeverity.BLOCKER,
            message="Mismatch in Q1 stem text",
            evidence={"question_number": 1},
        )
        ctx = build_repair_context(issue, q, max_tokens=600)

        assert ctx.question_number == 1
        assert ctx.rule == "text_layer_agreement"
        # Compact slice should not have verbose nulls or internal block lists
        q_slice = ctx.question_slice
        assert "number" in q_slice or "num" in q_slice
        assert "stem_en" not in q_slice
        assert ctx.estimated_tokens <= 600

    def test_enforce_hard_token_cap(self):
        q = Question(
            id="q_2",
            number=2,
            stem_text_en="Very long stem " * 100,
            options=[],
            source_pages=[1],
        )
        issue = Issue(
            id="i_2",
            stage="s8",
            rule="lexicon",
            severity=IssueSeverity.WARNING,
            message="unknown words",
        )
        # Even with long stem, builder truncates/enforces cap <= 300
        ctx = build_repair_context(issue, q, max_tokens=300)
        assert ctx.estimated_tokens <= 300
