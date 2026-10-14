"""Answer binding: Map parsed answer keys to ExamDocument questions."""

from __future__ import annotations

import logging
from typing import Any

from examforge.answers.parse_key import ParsedKeyEntry
from examforge.ir.schema import AnswerSpec, ExamDocument, Question

logger = logging.getLogger(__name__)

# Label scheme mapping dictionaries
DIGIT_TO_LETTER = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E", "6": "F"}
HINDI_TO_LETTER = {"क": "A", "ख": "B", "ग": "C", "घ": "D", "ङ": "E"}
ROMAN_TO_LETTER = {"i": "A", "ii": "B", "iii": "C", "iv": "D", "v": "E"}

LETTER_TO_DIGIT = {v: k for k, v in DIGIT_TO_LETTER.items()}
LETTER_TO_HINDI = {v: k for k, v in HINDI_TO_LETTER.items()}
LETTER_TO_ROMAN = {v: k for k, v in ROMAN_TO_LETTER.items()}


def resolve_option_label(raw_label: str, existing_labels: list[str]) -> str:
    """
    Resolve and normalize option label using question's existing option scheme.
    """
    if not existing_labels:
        return raw_label

    clean_raw = raw_label.strip("() \t")

    # 1. Exact match
    if clean_raw in existing_labels:
        return clean_raw

    # 2. Case-insensitive ASCII match
    for ex in existing_labels:
        if clean_raw.upper() == ex.upper():
            return ex

    # 3. Numeric to letter (1 -> A)
    if clean_raw in DIGIT_TO_LETTER:
        mapped = DIGIT_TO_LETTER[clean_raw]
        for ex in existing_labels:
            if mapped == ex.upper():
                return ex

    # 4. Hindi consonant to letter (क -> A)
    if clean_raw in HINDI_TO_LETTER:
        mapped = HINDI_TO_LETTER[clean_raw]
        for ex in existing_labels:
            if mapped == ex.upper():
                return ex

    # 5. Roman to letter (i -> A)
    if clean_raw.lower() in ROMAN_TO_LETTER:
        mapped = ROMAN_TO_LETTER[clean_raw.lower()]
        for ex in existing_labels:
            if mapped == ex.upper():
                return ex

    # 6. Letter to digit (A -> 1)
    if clean_raw.upper() in LETTER_TO_DIGIT:
        mapped = LETTER_TO_DIGIT[clean_raw.upper()]
        if mapped in existing_labels:
            return mapped

    # 7. Letter to Hindi (A -> क)
    if clean_raw.upper() in LETTER_TO_HINDI:
        mapped = LETTER_TO_HINDI[clean_raw.upper()]
        if mapped in existing_labels:
            return mapped

    return clean_raw


def find_matching_question(
    questions: list[Question],
    number: int,
    section: str | None = None,
) -> Question | None:
    """Find question matching (section, number) with fallback to number."""
    candidates = [q for q in questions if q.number == number]
    if not candidates:
        return None

    if len(candidates) == 1 and not section:
        return candidates[0]

    if section:
        sec_lower = section.strip().lower()
        for q in candidates:
            if q.section and q.section.strip().lower() == sec_lower:
                return q

    # Fallback to first candidate
    return candidates[0]


def bind_answers(
    document: ExamDocument,
    entries: list[ParsedKeyEntry],
    profile: Any | None = None,
) -> int:
    """
    Bind parsed answer key entries to questions in the ExamDocument.

    Returns the count of successfully bound questions.
    """
    bound_count = 0
    all_questions = document.questions

    for entry in entries:
        q = find_matching_question(
            all_questions,
            entry.question_number,
            entry.section,
        )
        if not q:
            logger.debug(
                "No question found matching Q%d (sec: %s)",
                entry.question_number,
                entry.section,
            )
            continue

        existing_labels = [opt.label for opt in q.options]

        if entry.is_bonus:
            # All options correct or bonus flag
            correct = existing_labels if existing_labels else ["BONUS"]
            spec = AnswerSpec(
                correct_options=correct,
                text_solution="BONUS",
            )
        elif entry.is_dropped:
            spec = AnswerSpec(
                correct_options=[],
                text_solution="DROPPED",
            )
        else:
            resolved_opts = [
                resolve_option_label(opt, existing_labels)
                for opt in entry.options
            ]
            spec = AnswerSpec(
                correct_options=resolved_opts,
                numeric_value=entry.numeric_value,
                numeric_range=entry.numeric_range,
            )

        q.answer = spec
        bound_count += 1

    return bound_count
