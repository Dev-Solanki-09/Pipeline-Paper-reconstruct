"""Tests for Question Bank Fingerprinting (Phase 12.2)."""

from __future__ import annotations

import numpy as np

from examforge.bank.fingerprint import (
    compute_figure_dhash,
    compute_number_signature,
    compute_simhash_64,
    hamming_distance_64,
    normalize_text_for_fingerprint,
)
from examforge.ir.schema import Option, Question


def test_normalize_text_for_fingerprint():
    raw = "  Find  the value of $\\alpha$ when $x = 10\\text{ m/s}$!  "
    norm = normalize_text_for_fingerprint(raw)
    assert "$" not in norm
    assert "  " not in norm
    assert "10" in norm
    assert "m/s" in norm


def test_normalize_devanagari_digits():
    raw = "प्रश्न १२: गति १० मी/से है।"
    norm = normalize_text_for_fingerprint(raw)
    assert "12" in norm
    assert "10" in norm


def test_compute_simhash_and_hamming_distance():
    text1 = "A particle of mass 2 kg moves with velocity 10 m/s in a circle of radius 5 m."
    text2 = "A particle of mass 2 kg moves with velocity 10 m/s in a circle of radius 6 m."
    text_unrelated = (
        "Explain the economic policies of the French Revolution during the Reign of Terror."
    )

    hash1 = compute_simhash_64(text1)
    hash2 = compute_simhash_64(text2)
    hash_unrelated = compute_simhash_64(text_unrelated)

    assert 0 <= hash1 < (1 << 64)
    assert 0 <= hash2 < (1 << 64)

    # Identical texts have distance 0
    assert hamming_distance_64(hash1, hash1) == 0

    # Small edit has small Hamming distance
    dist_near = hamming_distance_64(hash1, hash2)
    assert dist_near <= 10

    # Unrelated texts have large Hamming distance (~25-35 bits out of 64)
    dist_unrelated = hamming_distance_64(hash1, hash_unrelated)
    assert dist_unrelated >= 18


def test_compute_number_signature():
    q1 = Question(
        id="q1",
        number=1,
        stem_text_en="A 5 kg block moves at 10 m/s.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )
    sig1 = compute_number_signature(q1)

    # Different number
    q2 = Question(
        id="q2",
        number=1,
        stem_text_en="A 6 kg block moves at 10 m/s.",
        options=[
            Option(label="A", text_str_en="50 J"),
            Option(label="B", text_str_en="250 J"),
            Option(label="C", text_str_en="500 J"),
            Option(label="D", text_str_en="1000 J"),
        ],
    )
    sig2 = compute_number_signature(q2)

    assert sig1 != sig2
    assert "opts:4" in sig1
    assert "nums:5,10,50,250,500,1000" in sig1


def test_compute_figure_dhash():
    # 64x64 gradient image
    img = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (64, 1))
    dhash = compute_figure_dhash(img)
    assert isinstance(dhash, str)
    assert len(dhash) == 16  # 64 bits = 16 hex chars
