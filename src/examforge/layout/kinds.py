"""
Deterministic question-kind classifier for ExamForge v2 (Phase 6.7).

Heuristic classification for statements, assertion-reason, match list, numerical,
integer, true/false, fill-blank, passage-based, and MCQ questions without LLM invocation.
"""

from __future__ import annotations

import re
from typing import Sequence

from examforge.ir.schema import Option, QuestionKind

# Multilingual keywords for Assertion-Reason
_ASSERTION_RE = re.compile(
    r"(?:\bAssertion\b|\bअभिकथन\b|\bAssertion\s*\(?A\)?|\bReason\s*\(?R\)?|\bकारण\s*\(?R\)?)",
    re.IGNORECASE | re.UNICODE,
)

# Multilingual keywords for Statement-based
_STATEMENT_RE = re.compile(
    r"(?:\bStatement\s*[I|1|2|II]\b|\bकथन\s*[I|1|2|II]\b|\btwo\s+statements\b|\bदो\s+कथन\b)",
    re.IGNORECASE | re.UNICODE,
)

# Match the column / list keywords
_MATCH_RE = re.compile(
    r"(?:Match\s+List|Match\s+Column|सुमेलित\s+कीजिए|सूची\s*[-–:]?\s*[I|1]|Column\s*[A-Z])",
    re.IGNORECASE | re.UNICODE,
)

# Multi-correct cues
_MULTI_CORRECT_RE = re.compile(
    r"(?:more\s+than\s+one|one\s+or\s+more|multiple\s+correct|एक\s+से\s+अधिक)",
    re.IGNORECASE | re.UNICODE,
)

# True / False cues
_TRUE_FALSE_RE = re.compile(
    r"(?:True\s+or\s+False|State\s+True|सही\s+या\s+गलत|सत्य\s+या\s+असत्य)",
    re.IGNORECASE | re.UNICODE,
)

# Fill in the blank cues
_FILL_BLANK_RE = re.compile(
    r"(?:Fill\s+in\s+the\s+blank|रिक्त\s+स्थान|_{3,})",
    re.IGNORECASE | re.UNICODE,
)

# Integer cues
_INTEGER_RE = re.compile(
    r"(?:integer\s+value|integer\s+answer|non-negative\s+integer|पूर्णांक)",
    re.IGNORECASE | re.UNICODE,
)

# Numerical cues
_NUMERICAL_RE = re.compile(
    r"(?:numerical\s+value|rounded\s+off|decimal\s+place|दशमलव)",
    re.IGNORECASE | re.UNICODE,
)


def classify_question_kind(
    stem_text: str,
    options: Sequence[Option] = (),
    has_passage: bool = False,
) -> QuestionKind:
    """
    Classify question kind deterministically from stem text, options, and passage context.

    Returns the appropriate QuestionKind enum value.
    """
    stem = stem_text or ""
    stem_lower = stem.lower()

    # 1. Assertion-Reason
    if _ASSERTION_RE.search(stem) and ("reason" in stem_lower or "कारण" in stem):
        return QuestionKind.ASSERTION_REASON

    # 2. Statement-based
    if _STATEMENT_RE.search(stem):
        return QuestionKind.STATEMENT_BASED

    # 3. Match List / Column
    if _MATCH_RE.search(stem):
        return QuestionKind.MATCH

    # 4. Passage-based
    if has_passage or ("passage" in stem_lower and ("paragraph" in stem_lower or "based on" in stem_lower)):
        return QuestionKind.PASSAGE_BASED

    # 5. Multi-correct MCQ
    if options and _MULTI_CORRECT_RE.search(stem):
        return QuestionKind.MULTI_CORRECT

    # 6. True / False
    if _TRUE_FALSE_RE.search(stem):
        return QuestionKind.TRUE_FALSE
    if len(options) == 2:
        opt_texts = [o.text.strip().lower() for o in options]
        if set(opt_texts) in ({"true", "false"}, {"सत्य", "असत्य"}, {"सही", "गलत"}):
            return QuestionKind.TRUE_FALSE

    # 7. Fill in the blank
    if _FILL_BLANK_RE.search(stem):
        return QuestionKind.FILL_BLANK

    # 8. Numeric / Integer when no options are present
    if not options:
        if _INTEGER_RE.search(stem):
            return QuestionKind.INTEGER
        if _NUMERICAL_RE.search(stem):
            return QuestionKind.NUMERICAL
        # General question with 0 options in STEM exams is numerical/integer
        return QuestionKind.INTEGER if "integer" in stem_lower else QuestionKind.NUMERICAL

    # 9. Default: Single-correct MCQ
    return QuestionKind.SINGLE_CORRECT
