"""Marking scheme parsing and application for ExamForge."""

from __future__ import annotations

import logging
import re
from typing import Any

from examforge.answers.parse_key import _deva_to_ascii
from examforge.ir.schema import ExamDocument, Marks, Question

logger = logging.getLogger(__name__)

_SECTION_HEADER_RE = re.compile(
    r"(?:^|\n)(?:Section|Part|खण्ड|भाग)\s*([A-Za-z0-9]+(?:\s*\([^\)]+\))?)[:.\s\-]*",
    re.IGNORECASE,
)


def parse_marking_scheme(text: str) -> Marks:
    """
    Parse instruction text to extract positive, negative, and partial marks.
    """
    ascii_text = _deva_to_ascii(text)

    # Defaults
    positive = 4.0
    negative = 1.0
    partial = None

    # 1. Check for explicit "+X / -Y" or "(+X, -Y)"
    slash_match = re.search(
        r"\+(\d+(?:\.\d+)?)\s*[/,]\s*(?:-|−)?(\d+(?:\.\d+)?)",
        ascii_text,
    )
    if slash_match:
        positive = float(slash_match.group(1))
        negative = float(slash_match.group(2))
    else:
        # Check positive marks
        pos_match = re.search(
            r"\+(\d+(?:\.\d+)?)|"
            r"(?:correct(?:\s*answer)?|सही(?:\s*उत्तर)?)[^\d\n]*(\d+(?:\.\d+)?)|"
            r"(?:carries|each\s+correct\s+(?:answer\s+)?carries|प्रत्येक\s+सही\s+उत्तर\s+के\s+लिए)\s*(\d+(?:\.\d+)?)|"
            r"(\d+(?:\.\d+)?)\s*(?:marks?|अंक)?\s*(?:for\s+(?:each\s+)?correct|carries|each\b|सही)|"
            r"(\d+(?:\.\d+)?)\s*(?:marks?|अंक)",
            ascii_text,
            re.IGNORECASE,
        )
        if pos_match:
            val = next(g for g in pos_match.groups() if g is not None)
            positive = float(val)

        # Check negative marks
        no_neg = bool(
            re.search(
                r"no\s+negative\s+marking|negative\s*(?:marks?|marking)?[:\s]*0|ऋणात्मक\s+अंकन\s+नहीं",
                ascii_text,
                re.IGNORECASE,
            )
        )
        if no_neg:
            negative = 0.0
        else:
            neg_match = re.search(
                r"(?:-|−)\s*(\d+(?:\.\d+)?)|"
                r"(\d+(?:\.\d+)?)\s*(?:marks?|अंक)?\s*(?:will\s+be\s+)?(?:deducted|penalty|for\s+(?:each\s+)?incorrect|for\s+wrong|गलत|काटा)",
                ascii_text,
                re.IGNORECASE,
            )
            if neg_match:
                val = next(g for g in neg_match.groups() if g is not None)
                negative = float(val)

    # Check partial marks
    partial_match = re.search(
        r"(?:partial|आंशिक)\s*(?:marks?|credit|अंक)?[:\s]*\+?(\d+(?:\.\d+)?)",
        ascii_text,
        re.IGNORECASE,
    )
    if partial_match:
        partial = float(partial_match.group(1))

    return Marks(
        positive=positive,
        negative=negative,
        partial=partial,
    )


def parse_section_marking_schemes(text: str) -> dict[str, Marks]:
    """
    Parse section-specific marking schemes from instructions.
    """
    schemes: dict[str, Marks] = {}
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        # Single global scheme
        schemes["default"] = parse_marking_scheme(text)
        return schemes

    for i, m in enumerate(matches):
        sec_name = f"Section {m.group(1).strip()}"
        start_idx = m.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sec_text = text[start_idx:end_idx]
        schemes[sec_name] = parse_marking_scheme(sec_text)

    return schemes


def apply_marking_schemes(
    document: ExamDocument,
    default_marks: Marks | None = None,
    section_marks: dict[str, Marks] | None = None,
) -> int:
    """
    Apply marking schemes to all questions in ExamDocument.
    """
    count = 0
    section_marks = section_marks or {}

    for q in document.questions:
        target_marks: Marks | None = None
        if q.section:
            # Check exact or normalized match
            for sec_key, m_scheme in section_marks.items():
                if sec_key.lower() == q.section.lower() or sec_key.lower() in q.section.lower():
                    target_marks = m_scheme
                    break

        if not target_marks and default_marks:
            target_marks = default_marks

        if target_marks:
            q.marks = target_marks
            count += 1

    return count
