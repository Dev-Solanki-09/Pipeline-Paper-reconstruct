"""Tests for marking scheme parsing and application."""

from __future__ import annotations

import pytest

from examforge.answers.marks import (
    apply_marking_schemes,
    parse_marking_scheme,
    parse_section_marking_schemes,
)
from examforge.ir.schema import ExamDocument, Marks, Option, PageInfo, Question


def _make_dummy_doc() -> ExamDocument:
    pages = [PageInfo(page_number=1, width=800, height=1000)]
    questions = [
        Question(
            id="q_1",
            number=1,
            section="Section A",
            stem_text_en="Question 1",
            options=[Option(label="A", text_str_en="A")],
            source_pages=[1],
        ),
        Question(
            id="q_2",
            number=2,
            section="Section B",
            stem_text_en="Question 2",
            options=[Option(label="A", text_str_en="A")],
            source_pages=[1],
        ),
    ]
    return ExamDocument(
        id="test_doc",
        source_path="dummy.pdf",
        pages=pages,
        questions=questions,
    )


class TestMarkingSchemes:
    def test_parse_standard_plus_minus(self):
        text = "Marking Scheme: +4 / -1 for each question."
        marks = parse_marking_scheme(text)
        assert marks.positive == 4.0
        assert marks.negative == 1.0

    def test_parse_deduction_and_partial(self):
        text = "Each question carries 4 marks. 1 mark will be deducted for wrong answer. Partial marks: +1."
        marks = parse_marking_scheme(text)
        assert marks.positive == 4.0
        assert marks.negative == 1.0
        assert marks.partial == 1.0

    def test_parse_no_negative_marking(self):
        text = "Each correct answer carries 2 marks. There is no negative marking for incorrect response."
        marks = parse_marking_scheme(text)
        assert marks.positive == 2.0
        assert marks.negative == 0.0

    def test_parse_hindi_phrasing(self):
        text = "प्रत्येक सही उत्तर के लिए +4 अंक दिए जाएंगे तथा प्रत्येक गलत उत्तर के लिए 1 अंक काटा जाएगा।"
        marks = parse_marking_scheme(text)
        assert marks.positive == 4.0
        assert marks.negative == 1.0

    def test_parse_section_specific_schemes(self):
        text = (
            "Instructions:\n"
            "Section A: +4 marks for correct answer and -1 for incorrect answer.\n"
            "Section B: +3 marks for correct answer. No negative marking.\n"
        )
        sec_marks = parse_section_marking_schemes(text)
        assert "Section A" in sec_marks
        assert sec_marks["Section A"].positive == 4.0
        assert sec_marks["Section A"].negative == 1.0

        assert "Section B" in sec_marks
        assert sec_marks["Section B"].positive == 3.0
        assert sec_marks["Section B"].negative == 0.0

    def test_apply_marking_schemes_to_doc(self):
        doc = _make_dummy_doc()
        sec_marks = {
            "Section A": Marks(positive=4.0, negative=1.0),
            "Section B": Marks(positive=3.0, negative=0.0),
        }
        apply_marking_schemes(doc, section_marks=sec_marks)
        assert isinstance(doc.questions[0].marks, Marks)
        assert doc.questions[0].marks.positive == 4.0
        assert doc.questions[0].marks.negative == 1.0

        assert isinstance(doc.questions[1].marks, Marks)
        assert doc.questions[1].marks.positive == 3.0
        assert doc.questions[1].marks.negative == 0.0
