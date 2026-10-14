"""Tests for synthetic document generator."""

from __future__ import annotations

import pytest

from examforge.invariants import assert_invariants
from examforge.ir.schema import QuestionKind
from examforge.synth.generator import SyntheticDocumentGenerator


def test_generator_determinism():
    """Generating with the same seed must produce identical documents."""
    gen1 = SyntheticDocumentGenerator(seed=123)
    doc1 = gen1.generate(num_questions=8)

    gen2 = SyntheticDocumentGenerator(seed=123)
    doc2 = gen2.generate(num_questions=8)

    assert doc1.source_hash == doc2.source_hash
    assert len(doc1.questions) == len(doc2.questions)
    for q1, q2 in zip(doc1.questions, doc2.questions):
        assert q1.number == q2.number
        assert q1.kind == q2.kind
        assert len(q1.options) == len(q2.options)


def test_generator_structure_and_coverage():
    """Generator must produce diverse question kinds, passages, and figures."""
    gen = SyntheticDocumentGenerator(seed=42)
    doc = gen.generate(num_questions=10)

    assert len(doc.questions) >= 10
    kinds = {q.kind for q in doc.questions}
    # Must have multiple kinds including MCQ_SINGLE, MATCH or ASSERTION_REASON or PASSAGE_BASED
    assert len(kinds) >= 3

    # Passage must be populated
    assert len(doc.passages) >= 1
    p = doc.passages[0]
    assert len(p.question_refs) >= 2

    # Figures must be populated
    assert len(doc.figures) >= 1

    # Languages must be declared
    lang_codes = [l.code for l in doc.languages]
    assert "en" in lang_codes
    assert "hi" in lang_codes


def test_generated_document_passes_invariants():
    """Synthesized ExamDocument must strictly satisfy all IR invariants."""
    gen = SyntheticDocumentGenerator(seed=77)
    doc = gen.generate(num_questions=12)

    # Invariants enforcement should pass without raising any InvariantViolation
    assert_invariants(doc)
