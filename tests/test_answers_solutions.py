"""Tests for solution detection and parsing."""

from __future__ import annotations

import pytest

from examforge.answers.solutions import bind_solutions, parse_solution_blocks
from examforge.ir.schema import (
    ExamDocument,
    MathNode,
    Option,
    PageInfo,
    Question,
    QuestionKind,
    TextNode,
)


def _make_dummy_doc(num_questions: int = 3) -> ExamDocument:
    pages = [PageInfo(page_number=1, width=800, height=1000)]
    questions = []
    for i in range(1, num_questions + 1):
        q = Question(
            id=f"q_{i}",
            number=i,
            kind=QuestionKind.SINGLE_CORRECT,
            stem_text_en=f"Question {i}",
            options=[
                Option(label="A", text_str_en="A"),
                Option(label="B", text_str_en="B"),
            ],
            source_pages=[1],
        )
        questions.append(q)
    return ExamDocument(
        id="test_doc",
        source_path="dummy.pdf",
        pages=pages,
        questions=questions,
    )


class TestSolutionsParsing:
    def test_parse_solution_blocks_english(self):
        sample = (
            "Solution 1:\n"
            "Velocity is rate of change of displacement.\n"
            "$v = \\frac{dx}{dt}$\n\n"
            "Solution 2:\n"
            "Force is mass times acceleration.\n"
        )
        blocks = parse_solution_blocks(sample)
        assert len(blocks) == 2
        assert blocks[0].question_number == 1
        assert "displacement" in blocks[0].raw_text
        assert blocks[1].question_number == 2
        assert "acceleration" in blocks[1].raw_text

    def test_parse_solution_blocks_hindi(self):
        sample = (
            "हल 1:\n"
            "विस्थापन परिवर्तन की दर वेग कहलाती है।\n\n"
            "हल 2:\n"
            "बल द्रव्यमान और त्वरण का गुणनफल है।\n"
        )
        blocks = parse_solution_blocks(sample)
        assert len(blocks) == 2
        assert blocks[0].question_number == 1
        assert "विस्थापन" in blocks[0].raw_text
        assert blocks[1].question_number == 2

    def test_bind_solutions_to_document(self):
        doc = _make_dummy_doc(2)
        sample = (
            "Sol. 1:\n"
            "Kinetic energy is $E = \\frac{1}{2}mv^2$.\n\n"
            "Sol. 2:\n"
            "Work done is force times distance.\n"
        )
        count = bind_solutions(doc, sample)
        assert count == 2
        assert doc.questions[0].solution is not None
        assert len(doc.questions[0].solution) > 0
        # Check that math was recognized
        math_nodes = [n for n in doc.questions[0].solution if isinstance(n, MathNode)]
        assert len(math_nodes) >= 1
        assert "\\frac{1}{2}mv^2" in math_nodes[0].code
        # Check text node in second question
        text_nodes = [n for n in doc.questions[1].solution if isinstance(n, TextNode)]
        assert len(text_nodes) >= 1
        assert "Work done" in text_nodes[0].texts.get("en", "")
