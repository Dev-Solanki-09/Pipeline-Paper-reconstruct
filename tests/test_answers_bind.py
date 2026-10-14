"""Tests for answer key binding to ExamDocument questions."""

from __future__ import annotations

import pytest

from examforge.answers.bind import bind_answers
from examforge.answers.parse_key import ParsedKeyEntry
from examforge.ir.schema import (
    AnswerSpec,
    ExamDocument,
    Option,
    PageInfo,
    Question,
    QuestionKind,
)


def _make_dummy_doc(num_questions: int = 5, section: str | None = None) -> ExamDocument:
    pages = [PageInfo(page_number=1, width=800, height=1000)]
    questions = []
    for i in range(1, num_questions + 1):
        q = Question(
            id=f"q_{i}",
            number=i,
            section=section,
            kind=QuestionKind.SINGLE_CORRECT,
            stem_text_en=f"Question {i} text",
            options=[
                Option(label="A", text_str_en="Option A"),
                Option(label="B", text_str_en="Option B"),
                Option(label="C", text_str_en="Option C"),
                Option(label="D", text_str_en="Option D"),
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


class TestAnswerBinding:
    def test_bind_single_mcq_standard_labels(self):
        doc = _make_dummy_doc(3)
        entries = [
            ParsedKeyEntry(question_number=1, options=["A"]),
            ParsedKeyEntry(question_number=2, options=["C"]),
            ParsedKeyEntry(question_number=3, options=["D"]),
        ]
        bound_count = bind_answers(doc, entries)
        assert bound_count == 3
        assert isinstance(doc.questions[0].answer, AnswerSpec)
        assert doc.questions[0].answer.correct_options == ["A"]
        assert doc.questions[1].answer.correct_options == ["C"]
        assert doc.questions[2].answer.correct_options == ["D"]

    def test_bind_numeric_options_to_letters(self):
        doc = _make_dummy_doc(4)
        entries = [
            ParsedKeyEntry(question_number=1, options=["1"]),
            ParsedKeyEntry(question_number=2, options=["2"]),
            ParsedKeyEntry(question_number=3, options=["3"]),
            ParsedKeyEntry(question_number=4, options=["4"]),
        ]
        bound_count = bind_answers(doc, entries)
        assert bound_count == 4
        assert doc.questions[0].answer.correct_options == ["A"]
        assert doc.questions[1].answer.correct_options == ["B"]
        assert doc.questions[2].answer.correct_options == ["C"]
        assert doc.questions[3].answer.correct_options == ["D"]

    def test_bind_hindi_consonant_options_to_letters(self):
        doc = _make_dummy_doc(4)
        entries = [
            ParsedKeyEntry(question_number=1, options=["क"]),
            ParsedKeyEntry(question_number=2, options=["ख"]),
            ParsedKeyEntry(question_number=3, options=["ग"]),
            ParsedKeyEntry(question_number=4, options=["घ"]),
        ]
        bound_count = bind_answers(doc, entries)
        assert bound_count == 4
        assert doc.questions[0].answer.correct_options == ["A"]
        assert doc.questions[1].answer.correct_options == ["B"]
        assert doc.questions[2].answer.correct_options == ["C"]
        assert doc.questions[3].answer.correct_options == ["D"]

    def test_bind_numeric_values_and_ranges(self):
        doc = _make_dummy_doc(2)
        doc.questions[0].kind = QuestionKind.NUMERICAL
        doc.questions[1].kind = QuestionKind.NUMERICAL
        entries = [
            ParsedKeyEntry(question_number=1, numeric_value=42.0),
            ParsedKeyEntry(question_number=2, numeric_range=(3.14, 3.16)),
        ]
        bound_count = bind_answers(doc, entries)
        assert bound_count == 2
        assert doc.questions[0].answer.numeric_value == 42.0
        assert doc.questions[1].answer.numeric_range == (3.14, 3.16)

    def test_bind_sections_correctly(self):
        doc_phy = _make_dummy_doc(2, section="Physics")
        doc_chem = _make_dummy_doc(2, section="Chemistry")
        combined_doc = ExamDocument(
            id="combined",
            source_path="dummy.pdf",
            pages=doc_phy.pages,
            questions=doc_phy.questions + doc_chem.questions,
        )
        entries = [
            ParsedKeyEntry(question_number=1, section="Physics", options=["A"]),
            ParsedKeyEntry(question_number=2, section="Physics", options=["B"]),
            ParsedKeyEntry(question_number=1, section="Chemistry", options=["C"]),
            ParsedKeyEntry(question_number=2, section="Chemistry", options=["D"]),
        ]
        bound_count = bind_answers(combined_doc, entries)
        assert bound_count == 4
        assert combined_doc.questions[0].answer.correct_options == ["A"]
        assert combined_doc.questions[1].answer.correct_options == ["B"]
        assert combined_doc.questions[2].answer.correct_options == ["C"]
        assert combined_doc.questions[3].answer.correct_options == ["D"]

    def test_bind_bonus_and_dropped(self):
        doc = _make_dummy_doc(2)
        entries = [
            ParsedKeyEntry(question_number=1, is_bonus=True),
            ParsedKeyEntry(question_number=2, is_dropped=True),
        ]
        bound_count = bind_answers(doc, entries)
        assert bound_count == 2
        # Bonus marks all options correct
        assert set(doc.questions[0].answer.correct_options) == {"A", "B", "C", "D"}
        # Dropped marks text_solution as DROPPED
        assert doc.questions[1].answer.text_solution == "DROPPED"
