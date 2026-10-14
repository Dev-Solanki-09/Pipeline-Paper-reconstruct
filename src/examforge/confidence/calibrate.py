"""Multi-signal confidence calibration and Platt scaling for ExamForge nodes."""

from __future__ import annotations

import logging

import numpy as np

from examforge.ir.schema import ExamDocument, IssueSeverity, Question

logger = logging.getLogger(__name__)


class PlattScaler:
    """
    Parametric sigmoid calibration model (Platt scaling).

    Transforms raw composite scores into calibrated posterior probabilities:
        P(correct | score) = 1 / (1 + exp(-(a * score + b)))
    """

    def __init__(self, a: float = 6.0, b: float = -3.0) -> None:
        self.a = float(a)
        self.b = float(b)

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 300,
        lr: float = 0.1,
    ) -> PlattScaler:
        """Fit parameters a and b using gradient descent on binary log loss."""
        x_flat = np.asarray(X, dtype=float).ravel()
        y_flat = np.asarray(y, dtype=float).ravel()

        if len(x_flat) != len(y_flat) or len(x_flat) == 0:
            return self

        # Initialize
        a = 1.0
        b = 0.0

        for _ in range(epochs):
            z = np.clip(a * x_flat + b, -25.0, 25.0)
            p = 1.0 / (1.0 + np.exp(-z))
            p = np.clip(p, 1e-7, 1.0 - 1e-7)

            err = p - y_flat
            grad_a = np.mean(err * x_flat)
            grad_b = np.mean(err)

            a -= lr * grad_a
            b -= lr * grad_b

        # Ensure positive slope so higher score means higher probability
        if a < 0.1:
            a = 0.1

        self.a = float(a)
        self.b = float(b)
        return self

    def predict_proba(self, X: np.ndarray | float) -> np.ndarray | float:
        """Predict calibrated probabilities in [0.0, 1.0]."""
        x_arr = np.asarray(X, dtype=float)
        z = np.clip(self.a * x_arr + self.b, -25.0, 25.0)
        probs = 1.0 / (1.0 + np.exp(-z))
        if np.isscalar(X):
            return float(probs)
        return probs


def expected_calibration_error(
    probs: np.ndarray,
    y: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Calculate Expected Calibration Error (ECE).

    Bins probabilities into n_bins intervals, calculating weighted mean difference
    between predicted confidence and true empirical accuracy.
    """
    p = np.asarray(probs, dtype=float).ravel()
    labels = np.asarray(y, dtype=float).ravel()

    if len(p) == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total_samples = len(p)

    for i in range(n_bins):
        low, high = bins[i], bins[i + 1]
        mask = (p >= low) & (p <= high if i == n_bins - 1 else p < high)
        bin_count = np.sum(mask)

        if bin_count > 0:
            bin_acc = np.mean(labels[mask])
            bin_conf = np.mean(p[mask])
            ece += (bin_count / total_samples) * abs(bin_acc - bin_conf)

    return float(ece)


def extract_confidence_signals(
    question: Question,
    doc: ExamDocument,
) -> dict[str, float]:
    """
    Extract multi-source signals for a question:
    - ocr_confidence: mean confidence across blocks
    - issue_penalty: cumulative penalty from active issues touching this question
    - geometry_score: aspect ratio and bbox validity
    """
    # 1. OCR confidence
    blocks = []
    if question.stem_en:
        blocks.extend(question.stem_en)
    if question.stem_hi:
        blocks.extend(question.stem_hi)
    for opt in question.options:
        if opt.text_en:
            blocks.extend(opt.text_en)
        if opt.text_hi:
            blocks.extend(opt.text_hi)

    if blocks:
        ocr_conf = float(np.mean([b.confidence for b in blocks if b.confidence > 0] or [0.9]))
    else:
        ocr_conf = 0.90

    # 2. Issues touching this question
    q_issues = []
    for issue in doc.issues:
        ev = issue.evidence or {}
        if ev.get("question_number") == question.number or str(question.number) in issue.id:
            q_issues.append(issue)

    penalty = 0.0
    for issue in q_issues:
        if issue.severity == IssueSeverity.BLOCKER:
            penalty += 0.35
        elif issue.severity == IssueSeverity.WARNING:
            penalty += 0.15
    penalty = min(penalty, 1.0)

    # 3. Geometry score
    geom_score = 1.0
    for b in blocks:
        if b.bbox.width <= 0 or b.bbox.height <= 0:
            geom_score = 0.5
            break

    # 4. Composite raw score (normalized roughly to [0, 1])
    composite = 0.5 * ocr_conf + 0.35 * (1.0 - penalty) + 0.15 * geom_score

    return {
        "ocr_confidence": ocr_conf,
        "issue_penalty": penalty,
        "geometry_score": geom_score,
        "composite_score": composite,
    }


_DEFAULT_SCALER = PlattScaler(a=8.0, b=-4.5)


def compute_question_confidence(
    question: Question,
    doc: ExamDocument,
    scaler: PlattScaler | None = None,
) -> float:
    """Compute calibrated confidence score in [0.0, 1.0] for a question."""
    signals = extract_confidence_signals(question, doc)
    s = scaler or _DEFAULT_SCALER
    calibrated = s.predict_proba(signals["composite_score"])
    return float(np.clip(calibrated, 0.0, 1.0))
