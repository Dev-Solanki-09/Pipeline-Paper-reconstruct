"""Boilerplate phrase snapping to canonical exam phrase bank (Phase O7.4).

Standardizes common examination instructions and framing sentences
(English & Hindi) that suffer from minor OCR noise or character confusion.
"""

from __future__ import annotations

import re
from typing import Optional

from examforge.eval.metrics import compute_cer, normalize_text

# Canonical examination phrases mapped from normalized form
CANONICAL_PHRASES: list[str] = [
    # English standard exam instructions
    "Choose the correct option.",
    "Choose the correct answer.",
    "Choose the most appropriate answer from the options given below.",
    "Match List-I with List-II.",
    "Match Column-I with Column-II.",
    "Given below are two statements.",
    "One is labelled as Assertion A and the other is labelled as Reason R.",
    "In the light of the above statements, choose the most appropriate answer from the options given below.",
    "In the light of the above statements, choose the correct answer from the options given below.",
    "Statement I: ",
    "Statement II: ",
    "Assertion A: ",
    "Reason R: ",
    # Hindi standard exam instructions
    "निम्नलिखित में से सही विकल्प चुनिए।",
    "सूची-I को सूची-II से सुमेलित कीजिए।",
    "स्तंभ-I को स्तंभ-II से सुमेलित कीजिए।",
    "नीचे दो कथन दिए गए हैं।",
    "एक को अभिकथन (A) तथा दूसरे को कारण (R) कहा गया है।",
    "उपर्युक्त कथनों के आलोक में, नीचे दिए गए विकल्पों में से सबसे उपयुक्त उत्तर चुनिए।",
    "उपर्युक्त कथनों के आलोक में सही विकल्प चुनिए।",
    "कथन I: ",
    "कथन II: ",
    "अभिकथन A: ",
    "कारण R: ",
]


def snap_to_canonical_boilerplate(
    text: str, max_cer: float = 0.15, min_len: int = 15
) -> tuple[str, bool]:
    """Snap noisy input text to a canonical exam boilerplate phrase if match is high.

    Args:
        text: The candidate string (e.g. from OCR or stem line).
        max_cer: Maximum Character Error Rate to permit snapping (default 0.15 = 85% similarity).
        min_len: Minimum length to consider (avoids short ambiguous strings).

    Returns:
        (snapped_text, was_snapped)
    """
    clean_text = text.strip()
    if len(clean_text) < min_len:
        return text, False

    best_match: Optional[str] = None
    best_cer = 1.0

    for canonical in CANONICAL_PHRASES:
        # Fast length pre-filter
        len_diff = abs(len(clean_text) - len(canonical))
        if len_diff > max(len(canonical) * max_cer, 8):
            continue

        cer = compute_cer(canonical, clean_text)
        if cer < best_cer:
            best_cer = cer
            best_match = canonical

    if best_match is not None and best_cer <= max_cer:
        return best_match, True

    return text, False
