"""Tests for Rule R16: answer_binding validator."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    AnswerSpec,
    ExamDocument,
    IssueSeverity,
    Option,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.spec import Rule, RuleSeverity
from examforge.validators.r16_answer_binding import validate_answer_binding


def _make_doc_with_answers(valid: bool = True) -> ExamDocument:
    pages = [PageInfo(page_number=1, width=800, height=1000)]
    q1 = Question(
        id="q_1",
        number=1,
        kind=QuestionKind.SINGLE_CORRECT,
        stem_text_en="Q1",
        options=[Option(label="A"), Option(label="B"), Option(label="C"), Option(label="D")],
        answer=AnswerSpec(correct_options=["B"] if valid else ["E"]),
        source_pages=[1],
    )
    q2 = Question(
        id="q_2",
        number=2,
        kind=QuestionKind.NUMERICAL,
        stem_text_en="Q2",
        options=[],
        answer=AnswerSpec(numeric_value=25.0 if valid else None, numeric_range=(10.0, 5.0) if not valid else None),
        source_pages=[1],
    )
    return ExamDocument(
        id="test_doc",
        source_path="dummy.pdf",
        pages=pages,
        questions=[q1, q2],
    )


class TestR16AnswerBinding:
    def test_valid_document_has_no_issues(self):
        doc = _make_doc_with_answers(valid=True)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert len(issues) == 0

    def test_document_without_answers_has_no_issues(self):
        pages = [PageInfo(page_number=1, width=800, height=1000)]
        q = Question(
            id="q_1",
            number=1,
            stem_text_en="Q1",
            options=[Option(label="A")],
            source_pages=[1],
        )
        doc = ExamDocument(id="doc", source_path="dummy.pdf", pages=pages, questions=[q])
        issues = validate_answer_binding(doc)
        assert len(issues) == 0

    def test_detect_invalid_option_label(self):
        doc = _make_doc_with_answers(valid=False)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert any(i.id.startswith("r16_invalid_option_label") for i in issues)

    def test_detect_incomplete_key(self):
        doc = _make_doc_with_answers(valid=True)
        # Add third question with no answer
        q3 = Question(
            id="q_3",
            number=3,
            stem_text_en="Q3",
            options=[Option(label="A")],
            source_pages=[1],
        )
        doc.questions.append(q3)
        issues = validate_answer_binding(doc)
        assert any(i.id == "r16_incomplete_key" for i in issues)

    def test_detect_single_mcq_with_multiple_options(self):
        doc = _make_doc_with_answers(valid=True)
        doc.questions[0].answer = AnswerSpec(correct_options=["A", "B"])
        issues = validate_answer_binding(doc)
        assert any("single_mcq_multiple_answers" in i.id for i in issues)

    def test_detect_integer_kind_incompatibility(self):
        doc = _make_doc_with_answers(valid=True)
        doc.questions[1].kind = QuestionKind.INTEGER
        doc.questions[1].answer = AnswerSpec(numeric_value=3.14)
        issues = validate_answer_binding(doc)
        assert any("non_integer_answer" in i.id for i in issues)

    def test_detect_inverted_range(self):
        doc = _make_doc_with_answers(valid=True)
        doc.questions[1].answer = AnswerSpec(numeric_range=(10.0, 5.0))
        issues = validate_answer_binding(doc)
        assert any("inverted_range" in i.id for i in issues)
