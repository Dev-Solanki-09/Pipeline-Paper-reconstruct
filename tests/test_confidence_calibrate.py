"""Tests for multi-signal confidence calibration and Platt scaling."""

from __future__ import annotations

import numpy as np
import pytest

from examforge.confidence.calibrate import (
    PlattScaler,
    compute_question_confidence,
    expected_calibration_error,
    extract_confidence_signals,
)
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    Issue,
    IssueSeverity,
    Option,
    PageInfo,
    Question,
)


def _make_sample_doc_and_question(
    block_conf: float = 0.95,
    has_issues: bool = False,
) -> tuple[ExamDocument, Question]:
    pages = [PageInfo(page_number=1, width_px=595, height_px=842)]
    stem_block = Block(
        id="b_stem",
        page=1,
        bbox=BBox(x1=10, y1=10, x2=100, y2=30),
        text="What is velocity?",
        confidence=block_conf,
    )
    opt_block = Block(
        id="b_opt",
        page=1,
        bbox=BBox(x1=10, y1=35, x2=100, y2=50),
        text="(A) Rate of displacement",
        confidence=block_conf,
    )
    q = Question(
        id="q_1",
        number=1,
        stem_en=[stem_block],
        stem_text_en="What is velocity?",
        options=[Option(label="A", text_en=[opt_block], text_str_en="(A) Rate of displacement")],
        source_pages=[1],
    )
    issues = []
    if has_issues:
        issues.append(
            Issue(
                id="r11_q1_text_layer_disagreement",
                stage="s8_verify",
                rule="text_layer_agreement",
                severity=IssueSeverity.BLOCKER,
                message="Disagreement on Q1",
                evidence={"question_number": 1},
            )
        )
    doc = ExamDocument(
        id="doc_1",
        source_path="test.pdf",
        pages=pages,
        blocks=[stem_block, opt_block],
        questions=[q],
        issues=issues,
    )
    return doc, q


class TestConfidenceCalibration:
    def test_extract_signals(self):
        doc, q = _make_sample_doc_and_question(block_conf=0.92, has_issues=False)
        signals = extract_confidence_signals(q, doc)
        assert "ocr_confidence" in signals
        assert "issue_penalty" in signals
        assert "geometry_score" in signals
        assert pytest.approx(signals["ocr_confidence"], rel=1e-2) == 0.92
        assert signals["issue_penalty"] == 0.0

    def test_extract_signals_with_issues(self):
        doc, q = _make_sample_doc_and_question(block_conf=0.80, has_issues=True)
        signals = extract_confidence_signals(q, doc)
        assert signals["issue_penalty"] > 0.0

    def test_platt_scaler_fit_and_predict(self):
        # Synthetic feature (higher is better) and binary labels
        X = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        y = np.array([0, 0, 1, 1, 1])

        scaler = PlattScaler()
        scaler.fit(X, y)
        probs = scaler.predict_proba(X)

        assert len(probs) == 5
        assert np.all((probs >= 0.0) & (probs <= 1.0))
        # Monotonically increasing with feature value
        assert probs[0] < probs[-1]

    def test_expected_calibration_error(self):
        # Perfectly calibrated probabilities
        probs = np.array([0.1, 0.2, 0.8, 0.9])
        y = np.array([0, 0, 1, 1])
        ece = expected_calibration_error(probs, y, n_bins=5)
        assert ece >= 0.0
        assert ece < 0.25

    def test_compute_question_confidence(self):
        doc_clean, q_clean = _make_sample_doc_and_question(block_conf=0.98, has_issues=False)
        doc_bad, q_bad = _make_sample_doc_and_question(block_conf=0.50, has_issues=True)

        conf_clean = compute_question_confidence(q_clean, doc_clean)
        conf_bad = compute_question_confidence(q_bad, doc_bad)

        assert 0.0 <= conf_clean <= 1.0
        assert 0.0 <= conf_bad <= 1.0
        assert conf_clean > conf_bad
        assert conf_clean >= 0.85
