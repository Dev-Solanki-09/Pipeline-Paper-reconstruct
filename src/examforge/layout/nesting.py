"""
Nesting and internal choice detection for ExamForge v2 (Phase 6.5).

Detects sub-parts (a)(b)(c), (i)(ii), and internal choice alternatives (OR / अथवा).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SubPart:
    """A nested sub-part within a multi-part question."""

    label: str
    text: str


_INTERNAL_CHOICE_RE = re.compile(
    r"(?:^|\n)\s*(?:OR|अथवा|\bOR\b|\bअथवा\b)\s*(?:\n|$)",
    re.IGNORECASE | re.UNICODE,
)


def detect_internal_choice(text: str) -> list[str]:
    """
    Split text into alternative question choices separated by OR / अथवा.

    Returns list of alternative choice texts (length >= 2 if internal choice present, else [text]).
    """
    if not text:
        return []

    splits = _INTERNAL_CHOICE_RE.split(text)
    cleaned = [s.strip() for s in splits if s.strip()]
    return cleaned if len(cleaned) >= 2 else [text.strip()]


def detect_subparts(
    text: str,
    labels: list[str] | None = None,
) -> list[SubPart]:
    """
    Detect sequential sub-part items like (a)(b)(c) or (i)(ii)(iii) in question text.

    Returns list of SubPart items if at least 2 sequential subparts found, else empty list.
    """
    if not text:
        return []

    target_labels = labels or ["(a)", "(b)", "(c)", "(d)"]

    # Normalize labels to regex patterns
    # e.g. "(a)" -> r"(?:^|\n)\s*\(a\)\s*"
    matches = []
    for lbl in target_labels:
        escaped = re.escape(lbl)
        pattern = re.compile(rf"(?:^|\n)\s*{escaped}\s*", re.IGNORECASE)
        m = pattern.search(text)
        if m:
            matches.append((lbl, m.start(), m.end()))

    # Sort matches by position in text
    matches.sort(key=lambda x: x[1])

    if len(matches) < 2:
        return []

    subparts: list[SubPart] = []
    for i, (lbl, start, end) in enumerate(matches):
        next_start = matches[i + 1][1] if i + 1 < len(matches) else len(text)
        part_text = text[end:next_start].strip()
        subparts.append(SubPart(label=lbl, text=part_text))

    return subparts
