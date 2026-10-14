"""
Document parts and page classification for ExamForge v2 (Phase 6.8).

Classifies pages and blocks into cover, instructions, section headers, questions,
answer keys, solutions, rough work, and OMR partitions.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from examforge.ir.schema import Block, DocumentPart, PageClassification

logger = logging.getLogger(__name__)

# Cover page keywords
_COVER_RE = re.compile(
    r"(?:TEST\s+BOOKLET|QUESTION\s+BOOKLET|EXAM\s+PAPER|CANDIDATE'?S?\s+(?:NAME|ROLL)|"
    r"ROLL\s+NO|DO\s+NOT\s+OPEN|TIME\s+ALLOWED|MAXIMUM\s+MARKS|SEAL)",
    re.IGNORECASE,
)

# Instructions keywords
_INSTRUCTIONS_RE = re.compile(
    r"(?:IMPORTANT\s+INSTRUCTIONS|GENERAL\s+INSTRUCTIONS|READ\s+THE\s+FOLLOWING\s+INSTRUCTIONS|"
    r"MARKING\s+SCHEME|NEGATIVE\s+MARKING|OMR\s+SHEET|BLUE\s*[/]\s*BLACK\s+BALL\s+POINT)",
    re.IGNORECASE,
)

# Answer key keywords
_ANSWER_KEY_RE = re.compile(
    r"(?:ANSWER\s+KEY|ANS(?:WER)?\s+KEY|KEY\s+ANSWERS?|FINAL\s+KEY|"
    r"Q\.?\s*No\.?\s*\|\s*Ans(?:wer)?)",
    re.IGNORECASE,
)

# Rough work keywords
_ROUGH_WORK_RE = re.compile(
    r"(?:SPACE\s+FOR\s+ROUGH\s+WORK|ROUGH\s+WORK|रफ\s+कार्य)",
    re.IGNORECASE | re.UNICODE,
)

# Solutions keywords
_SOLUTIONS_RE = re.compile(
    r"(?:HINTS\s+&\s+SOLUTIONS|DETAILED\s+SOLUTIONS|EXPLANATIONS|हल\s+एवं\s+उत्तर)",
    re.IGNORECASE | re.UNICODE,
)

# Question detection pattern
_QUESTION_DETECT_RE = re.compile(
    r"^\s*(?:Q\.?\s*)?\d{1,3}\s*[.):]",
    re.MULTILINE,
)


def classify_page_part(
    blocks: list[Block],
    page_num: int,
    total_pages: int,
) -> PageClassification:
    """
    Classify a single page into its semantic PageClassification enum.
    """
    if not blocks:
        return PageClassification.BLANK

    combined_text = "\n".join(b.text.strip() for b in blocks if b.text)

    # 1. Rough work check
    if _ROUGH_WORK_RE.search(combined_text):
        # If there are almost no questions on the page, it's rough work
        if len(_QUESTION_DETECT_RE.findall(combined_text)) <= 1:
            return PageClassification.ROUGH_WORK

    # 2. Answer key check
    if _ANSWER_KEY_RE.search(combined_text):
        return PageClassification.ANSWER_KEY

    # 3. Solutions check
    if _SOLUTIONS_RE.search(combined_text):
        return PageClassification.SOLUTIONS

    # 4. Cover page check (page 1 or first non-blank page)
    if page_num == 1 and _COVER_RE.search(combined_text):
        # Must have few or zero question starts
        if len(_QUESTION_DETECT_RE.findall(combined_text)) < 2:
            return PageClassification.COVER

    # 5. Instructions check (early pages)
    if page_num <= 3 and _INSTRUCTIONS_RE.search(combined_text):
        if len(_QUESTION_DETECT_RE.findall(combined_text)) < 3:
            return PageClassification.INSTRUCTIONS

    # 6. Default: Questions page if questions present or general content
    q_matches = len(_QUESTION_DETECT_RE.findall(combined_text))
    if q_matches >= 1:
        return PageClassification.QUESTIONS

    # If it's page 1, default to COVER if no questions
    if page_num == 1:
        return PageClassification.COVER

    return PageClassification.QUESTIONS


def classify_document_part(
    kind: Literal[
        "cover",
        "instructions",
        "section_header",
        "answer_key",
        "solutions",
        "rough_work",
        "omr",
    ],
    blocks: list[Block],
    pages: list[int],
) -> DocumentPart:
    """Construct a DocumentPart entity."""
    return DocumentPart(
        kind=kind,
        pages=sorted(list(set(pages))),
        blocks=blocks,
    )
