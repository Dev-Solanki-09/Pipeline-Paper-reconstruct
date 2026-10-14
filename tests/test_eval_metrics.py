"""Tests for evaluation metrics (CER, WER, IoU, Sequence Accuracy, Table similarity)."""

from __future__ import annotations

import pytest

from examforge.eval.metrics import (
    compute_bbox_iou,
    compute_cer,
    compute_count_match,
    compute_formula_exact_match,
    compute_sequence_accuracy,
    compute_table_structure_similarity,
    compute_wer,
    levenshtein_distance,
    normalize_text,
)
from examforge.ir.schema import BBox


def test_normalize_text():
    assert normalize_text("  Hello\n\tWorld  ") == "hello world"
    assert normalize_text("") == ""


def test_levenshtein_distance():
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("abc", "") == 3


def test_cer_and_wer_exact():
    ref = "A particle moves in a circle of radius R with constant speed v."
    hyp = "A particle moves in a circle of radius R with constant speed v."
    assert compute_cer(ref, hyp) == 0.0
    assert compute_wer(ref, hyp) == 0.0


def test_cer_and_wer_partial_error():
    ref = "the quick brown fox"
    hyp = "the quick brown box"
    # One char change (f -> b), one word change (fox -> box)
    cer = compute_cer(ref, hyp)
    wer = compute_wer(ref, hyp)
    assert 0.0 < cer < 0.2
    assert wer == 0.25  # 1 word wrong out of 4


def test_sequence_accuracy_and_count():
    assert compute_sequence_accuracy([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert compute_sequence_accuracy([1, 2, 3], [1, 2, 4]) == 0.0
    assert compute_count_match(10, 10) == 1.0
    assert compute_count_match(10, 9) == 0.0


def test_bbox_iou():
    b1 = BBox(x1=0.0, y1=0.0, x2=10.0, y2=10.0)
    b2 = BBox(x1=0.0, y1=0.0, x2=10.0, y2=10.0)
    assert compute_bbox_iou(b1, b2) == 1.0

    # Non-overlapping
    b3 = BBox(x1=20.0, y1=20.0, x2=30.0, y2=30.0)
    assert compute_bbox_iou(b1, b3) == 0.0

    # Half overlap: 50% overlap along x
    b4 = BBox(x1=5.0, y1=0.0, x2=15.0, y2=10.0)
    # intersection: 5*10 = 50. Union: 100 + 100 - 50 = 150. IoU = 50/150 = 1/3
    assert abs(compute_bbox_iou(b1, b4) - 0.3333) < 0.001


def test_formula_exact_match():
    assert compute_formula_exact_match(r"E = mc^2", r"E=mc^2") == 1.0
    assert compute_formula_exact_match(r"\left( x \right)", r"(x)") == 1.0
    assert compute_formula_exact_match(r"x + 1", r"x - 1") == 0.0


def test_table_structure_similarity():
    ref_table = [["A", "B"], ["C", "D"]]
    hyp_table = [["A", "B"], ["C", "D"]]
    assert compute_table_structure_similarity(ref_table, hyp_table) == 1.0

    # Different rows
    diff_table = [["A", "B"]]
    sim = compute_table_structure_similarity(ref_table, diff_table)
    assert 0.0 < sim < 1.0
