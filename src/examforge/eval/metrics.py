"""Deterministic evaluation metrics for ExamForge.

Implements Sequence Accuracy, CER, WER, Option Accuracy, Kind Accuracy,
Figure IoU, Formula Exact Match, and Table Tree Similarity.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

from examforge.ir.schema import BBox, Question, QuestionKind


def normalize_text(text: str) -> str:
    """NFC normalization, lowercasing, and collapsing whitespace."""
    if not text:
        return ""
    # NFC Unicode normalization
    text = unicodedata.normalize("NFC", text)
    # Collapse multiple whitespace characters to single space
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def levenshtein_distance(s1: Sequence[Any], s2: Sequence[Any]) -> int:
    """Standard dynamic programming Levenshtein distance on sequence of tokens/chars."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (0 if c1 == c2 else 1)
            current_row[j + 1] = min(insertions, deletions, substitutions)
        previous_row = current_row

    return previous_row[-1]


def compute_cer(reference: str, hypothesis: str) -> float:
    """
    Character Error Rate (CER) = Levenshtein(ref, hyp) / max(1, len(ref)).
    Clamped to [0.0, 1.0].
    """
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)
    if not ref_norm and not hyp_norm:
        return 0.0
    if not ref_norm:
        return 1.0

    dist = levenshtein_distance(ref_norm, hyp_norm)
    return min(1.0, dist / len(ref_norm))


def compute_wer(reference: str, hypothesis: str) -> float:
    """
    Word Error Rate (WER) = Levenshtein(ref_words, hyp_words) / max(1, len(ref_words)).
    Clamped to [0.0, 1.0].
    """
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()

    if not ref_words and not hyp_words:
        return 0.0
    if not ref_words:
        return 1.0

    dist = levenshtein_distance(ref_words, hyp_words)
    return min(1.0, dist / len(ref_words))


def compute_sequence_accuracy(ref_numbers: list[int], hyp_numbers: list[int]) -> float:
    """Returns 1.0 if extracted question-number sequence equals reference exactly, else 0.0."""
    return 1.0 if ref_numbers == hyp_numbers else 0.0


def compute_count_match(ref_count: int, hyp_count: int) -> float:
    """Returns 1.0 if counts match exactly, else 0.0."""
    return 1.0 if ref_count == hyp_count else 0.0


def compute_option_accuracy(ref_q: Question, hyp_q: Question) -> float:
    """
    Option Accuracy: Evaluates whether option count and option label sequence match.
    Returns 1.0 on exact match, partial score for matching labels, or 0.0.
    """
    if not ref_q.options and not hyp_q.options:
        return 1.0
    if not ref_q.options or not hyp_q.options:
        return 0.0

    ref_labels = [opt.label.strip() for opt in ref_q.options]
    hyp_labels = [opt.label.strip() for opt in hyp_q.options]

    if ref_labels == hyp_labels:
        return 1.0

    # Label overlap score
    common = sum(1 for h in hyp_labels if h in ref_labels)
    return common / max(len(ref_labels), len(hyp_labels))


def compute_bbox_iou(b1: BBox, b2: BBox) -> float:
    """Intersection over Union (IoU) between two bounding boxes."""
    inter_x1 = max(b1.x1, b2.x1)
    inter_y1 = max(b1.y1, b2.y1)
    inter_x2 = min(b1.x2, b2.x2)
    inter_y2 = min(b1.y2, b2.y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, (b1.x2 - b1.x1) * (b1.y2 - b1.y1))
    area2 = max(0.0, (b2.x2 - b2.x1) * (b2.y2 - b2.y1))
    union_area = area1 + area2 - inter_area

    if union_area <= 1e-6:
        return 0.0
    return inter_area / union_area


def compute_formula_exact_match(ref_latex: str, hyp_latex: str) -> float:
    """Check canonicalized LaTeX math equality."""
    def clean(s: str) -> str:
        s = re.sub(r"\s+", "", s)
        s = s.replace(r"\left", "").replace(r"\right", "")
        return s

    return 1.0 if clean(ref_latex) == clean(hyp_latex) else 0.0


def compute_table_structure_similarity(
    ref_rows: list[list[Any]],
    hyp_rows: list[list[Any]],
) -> float:
    """TEDS-style structural similarity comparing row counts and column dimensions."""
    if not ref_rows and not hyp_rows:
        return 1.0
    if not ref_rows or not hyp_rows:
        return 0.0

    row_score = 1.0 - min(1.0, abs(len(ref_rows) - len(hyp_rows)) / max(len(ref_rows), len(hyp_rows)))
    ref_cols = [len(r) for r in ref_rows]
    hyp_cols = [len(r) for r in hyp_rows]
    avg_ref_col = sum(ref_cols) / len(ref_cols) if ref_cols else 0
    avg_hyp_col = sum(hyp_cols) / len(hyp_cols) if hyp_cols else 0

    col_score = 1.0 - min(1.0, abs(avg_ref_col - avg_hyp_col) / max(1.0, avg_ref_col, avg_hyp_col))
    return 0.5 * (row_score + col_score)
