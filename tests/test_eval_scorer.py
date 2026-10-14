"""Tests for ExamScorer and compare tools."""

from __future__ import annotations

import pytest

from examforge.eval.compare import compare_metrics
from examforge.eval.scorer import ExamScorer
from examforge.ir.schema import Question, QuestionKind, TextNode
from examforge.synth.generator import SyntheticDocumentGenerator


def test_scorer_self_consistency():
    """Scoring a document against itself must yield perfect 1.0 aggregate and 0.0 error rates."""
    gen = SyntheticDocumentGenerator(seed=42)
    doc = gen.generate(num_questions=6)

    scorer = ExamScorer()
    result = scorer.score(reference=doc, hypothesis=doc)

    assert result.sequence_accuracy == 1.0
    assert result.count_match == 1.0
    assert result.cer_mean == 0.0
    assert result.wer_mean == 0.0
    assert result.option_accuracy == 1.0
    assert result.kind_accuracy == 1.0
    assert result.aggregate_score == 1.0


def test_scorer_detects_errors():
    """Scoring with missing questions or altered text must degrade metrics."""
    gen = SyntheticDocumentGenerator(seed=42)
    ref = gen.generate(num_questions=6)
    hyp = gen.generate(num_questions=6)

    # Mutate hypothesis: remove last question
    hyp.questions = hyp.questions[:-1]
    # Mutate stem of first question
    hyp.questions[0].stem = [TextNode(texts={"en": "Completely altered question stem text."})]

    scorer = ExamScorer()
    result = scorer.score(reference=ref, hypothesis=hyp)

    assert result.count_match == 0.0
    assert result.sequence_accuracy == 0.0
    assert result.cer_mean > 0.0
    assert result.aggregate_score < 1.0


def test_compare_metrics_regression():
    baseline = {
        "sequence_accuracy": 1.0,
        "count_match": 1.0,
        "cer_mean": 0.01,
        "option_accuracy": 0.98,
        "aggregate_score": 0.95,
    }
    # No regression
    current_ok = {
        "sequence_accuracy": 1.0,
        "count_match": 1.0,
        "cer_mean": 0.012,  # within 0.005 tolerance
        "option_accuracy": 0.98,
        "aggregate_score": 0.95,
    }
    passed, reg = compare_metrics(current_ok, baseline)
    assert passed
    assert len(reg) == 0

    # Regression: sequence accuracy dropped to 0.80
    current_bad = {
        "sequence_accuracy": 0.80,
        "count_match": 1.0,
        "cer_mean": 0.01,
        "option_accuracy": 0.98,
        "aggregate_score": 0.88,
    }
    passed_bad, reg_bad = compare_metrics(current_bad, baseline)
    assert not passed_bad
    assert len(reg_bad) >= 1
