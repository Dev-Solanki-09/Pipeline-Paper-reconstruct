"""
S4 Exam Structure: Segment blocks into Questions.

For a JEE/NEET paper, questions follow predictable patterns:
- Question numbers: "1.", "Q.1", "(1)", "Q1.", etc.
- Options: "(A)", "(B)", "(C)", "(D)" or "(1)", "(2)", "(3)", "(4)"
- Sections: "SECTION - A", "SECTION A", "PART-1 : PHYSICS", etc.

This stage:
1. Filters blocks from question pages and sorts them by page + reading order
2. Tracks section headers
3. Identifies question-start boundaries using regex
4. Groups blocks between question starts into stems + options
5. Detects question kind (MCQ_SINGLE, MCQ_MULTI, NUMERIC, PASSAGE, etc.)
6. Verifies numbering continuity and logs issues for gaps/duplicates
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from examforge.ir.schema import (
    Block,
    BlockStatus,
    Issue,
    IssueSeverity,
    Option,
    PageClassification,
    Question,
    QuestionKind,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Question number boundary patterns
PATTERN_DOT = re.compile(r"^\s*(\d{1,3})\s*[.):\n]", re.MULTILINE)
PATTERN_Q_DOT = re.compile(r"^\s*Q\.?\s*(\d{1,3})\s*[.):\n]?", re.IGNORECASE | re.MULTILINE)
PATTERN_PAREN = re.compile(r"^\s*\((\d{1,3})\)\s*", re.MULTILINE)

CANDIDATE_PATTERNS = [
    (PATTERN_DOT, "DOT"),
    (PATTERN_Q_DOT, "Q_DOT"),
    (PATTERN_PAREN, "PAREN"),
]

# Section headers
SECTION_RE = re.compile(
    r"(?:PART\s*[-–:]?\s*[0-9IVX]+|SECTION\s*[-–:]?\s*[A-Za-z0-9()]+|PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY)",
    re.IGNORECASE,
)

# Option patterns
OPTION_ALPHA_RE = re.compile(r"(?:^|[\s\n])\(([A-D])\)\s*", re.MULTILINE)
OPTION_LOWER_RE = re.compile(r"(?:^|[\s\n])\(([a-d])\)\s*", re.MULTILINE)
OPTION_NUM_RE = re.compile(r"(?:^|[\s\n])\(([1-4])\)\s*", re.MULTILINE)


@dataclass
class RawQuestion:
    """Intermediate representation before creating Question objects."""

    number: int
    stem_blocks: list[Block] = field(default_factory=list)
    option_blocks: dict[str, list[Block]] = field(default_factory=dict)
    stem_text: str = ""
    options_text: dict[str, str] = field(default_factory=dict)
    source_pages: list[int] = field(default_factory=list)
    section: Optional[str] = None


class S4Structure(Stage):
    """
    Stage 4: Segment text blocks into structured Question objects.
    """

    name = "s4_structure"

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S4 requires blocks to be present in the document."""
        violations = []
        if not ctx.document.blocks:
            violations.append("No blocks found in document -- S3 Parse must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict = {}

        # 1. Filter blocks: question pages only, not dropped
        question_page_numbers = {
            p.page_number
            for p in doc.pages
            if p.classification == PageClassification.QUESTIONS
        }

        # If no pages classified as QUESTIONS, check for any non-cover, non-rough pages
        if not question_page_numbers:
            question_page_numbers = {
                p.page_number
                for p in doc.pages
                if p.classification not in (PageClassification.COVER, PageClassification.ROUGH_WORK, PageClassification.BLANK)
            }

        candidate_blocks = [
            b
            for b in doc.blocks
            if b.page in question_page_numbers and b.status != BlockStatus.DROPPED
        ]

        # 2. Sort blocks by page, y1, x1
        candidate_blocks.sort(key=lambda b: (b.page, b.bbox.y1, b.bbox.x1))

        if not candidate_blocks:
            logger.warning("S4Structure: No candidate blocks found for segmentation.")
            return StageResult(document=doc, metrics={"questions_extracted": 0}, issues=issues)

        # 3. Find best question pattern
        all_text = "\n".join(b.text for b in candidate_blocks)
        pattern = _find_question_pattern(all_text)

        if pattern is None:
            # Fallback to PATTERN_DOT
            pattern = PATTERN_DOT

        # 4. Segment blocks into raw questions
        raw_questions = _segment_questions(candidate_blocks, pattern)

        # 5. Convert RawQuestion to Question IR objects
        questions: list[Question] = []
        for rq in raw_questions:
            stem_text, options = _parse_options_from_raw(rq)
            kind = _detect_question_kind(stem_text, options)

            q = Question(
                id=f"q{rq.number}",
                number=rq.number,
                section=rq.section,
                kind=kind,
                stem_en=rq.stem_blocks,
                stem_text_en=stem_text,
                options=options,
                source_pages=sorted(list(set(rq.source_pages))),
            )
            questions.append(q)

        # 6. Check numbering continuity
        continuity_issues = _check_numbering_continuity(questions)
        issues.extend(continuity_issues)

        # Save questions to document
        doc.questions = questions

        metrics["questions_extracted"] = len(questions)
        metrics["sections_found"] = len({q.section for q in questions if q.section})
        mcq_count = sum(1 for q in questions if q.kind == QuestionKind.MCQ_SINGLE)
        metrics["mcq_count"] = mcq_count

        logger.info(
            "  S4 Structure complete: %d questions extracted (%d MCQ, %d continuity issues)",
            len(questions),
            mcq_count,
            len(continuity_issues),
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Check that questions were created if blocks were available."""
        violations = []
        doc = result.document

        question_text_pages = sum(
            1
            for p in doc.pages
            if p.classification == PageClassification.QUESTIONS
            and p.has_text_layer
            and p.text_layer_valid
        )

        if question_text_pages > 0 and len(doc.blocks) > 20 and not doc.questions:
            violations.append(
                f"No questions extracted despite {question_text_pages} question pages "
                f"and {len(doc.blocks)} blocks."
            )

        return violations


def _find_question_pattern(text: str) -> re.Pattern | None:
    """Try multiple question-number patterns and return the best match.

    Returns the pattern matching >= 5 times, or the most frequent if none reach 5.
    Returns None if no patterns match.
    """
    best_pattern = None
    max_count = 0

    for pat, _ in CANDIDATE_PATTERNS:
        matches = pat.findall(text)
        count = len(matches)
        if count >= 5:
            return pat
        if count > max_count:
            max_count = count
            best_pattern = pat

    if max_count > 0:
        return best_pattern
    return None


def _detect_sections(blocks: list[Block]) -> list[tuple[int, str]]:
    """Find section headers and their block indices.

    Returns list of (block_index, section_name).
    """
    sections = []
    for idx, block in enumerate(blocks):
        text = block.text.strip()
        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if len(line_str) < 60 and SECTION_RE.search(line_str):
                # Avoid matching inside question stems
                if not re.match(r"^\s*\d{1,3}\s*[.):]", line_str):
                    sections.append((idx, line_str))
                    break
    return sections


def _segment_questions(
    blocks: list[Block],
    pattern: re.Pattern,
) -> list[RawQuestion]:
    """Split a sorted block stream into raw question segments."""
    raw_questions: list[RawQuestion] = []
    current_section: Optional[str] = None
    current_rq: Optional[RawQuestion] = None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        # Check if block is a section header
        if len(text) < 80 and SECTION_RE.search(text) and not pattern.match(text):
            current_section = text
            continue

        # Check if block starts a new question
        match = pattern.match(text)
        if match:
            # Save previous question if exists
            if current_rq is not None:
                raw_questions.append(current_rq)

            try:
                num = int(match.group(1))
            except (ValueError, IndexError):
                num = len(raw_questions) + 1

            # Strip the question number prefix from the starting block text for clean stem
            prefix_len = match.end()
            stem_remainder = text[prefix_len:].strip()

            current_rq = RawQuestion(
                number=num,
                stem_blocks=[block],
                stem_text=stem_remainder,
                source_pages=[block.page],
                section=current_section,
            )
        else:
            if current_rq is not None:
                current_rq.stem_blocks.append(block)
                if current_rq.stem_text:
                    current_rq.stem_text += "\n" + text
                else:
                    current_rq.stem_text = text
                if block.page not in current_rq.source_pages:
                    current_rq.source_pages.append(block.page)

    if current_rq is not None:
        raw_questions.append(current_rq)

    return raw_questions


def _parse_options_from_raw(rq: RawQuestion) -> tuple[str, list[Option]]:
    """Parse stem and options from a raw question.

    Returns (clean_stem_text, list of Option objects).
    """
    full_text = rq.stem_text

    # Determine option marker regex to use
    alpha_matches = list(OPTION_ALPHA_RE.finditer(full_text))
    lower_matches = list(OPTION_LOWER_RE.finditer(full_text))
    num_matches = list(OPTION_NUM_RE.finditer(full_text))

    chosen_matches = []
    if len(alpha_matches) >= 2:
        chosen_matches = alpha_matches
    elif len(lower_matches) >= 2:
        chosen_matches = lower_matches
    elif len(num_matches) >= 2:
        chosen_matches = num_matches

    if not chosen_matches:
        # No options detected -> all text is stem
        # Clean up any trailing space for rough work
        stem = re.sub(r"SPACE FOR ROUGH WORK.*$", "", full_text, flags=re.IGNORECASE | re.DOTALL).strip()
        return stem, []

    # Stem is everything before the first option
    first_opt = chosen_matches[0]
    stem = full_text[: first_opt.start()].strip()
    # Clean up trailing footer/rough work if caught before
    stem = re.sub(r"SPACE FOR ROUGH WORK.*$", "", stem, flags=re.IGNORECASE | re.DOTALL).strip()

    options: list[Option] = []
    for i, match in enumerate(chosen_matches):
        label = match.group(1).upper()
        start = match.end()
        end = chosen_matches[i + 1].start() if i + 1 < len(chosen_matches) else len(full_text)
        opt_text = full_text[start:end].strip()

        # Clean trailing space for rough work or page numbers
        opt_text = re.sub(r"SPACE FOR ROUGH WORK.*$", "", opt_text, flags=re.IGNORECASE | re.DOTALL).strip()
        opt_text = re.sub(r"\d+/\d+\s*$", "", opt_text).strip()

        options.append(
            Option(
                label=label,
                text_str_en=opt_text,
            )
        )

    return stem, options


def _parse_options(blocks: list[Block]) -> tuple[list[Block], list[Option]]:
    """Separate stem blocks from option blocks.

    Compatibility helper matching the signature in MASTER_BUILD_PLAN.md.
    """
    full_text = "\n".join(b.text for b in blocks)
    stem_text, options = _parse_options_from_raw(RawQuestion(number=1, stem_text=full_text, stem_blocks=blocks))

    # Identify which blocks are strictly option blocks vs stem blocks
    stem_blocks = []
    for b in blocks:
        if OPTION_ALPHA_RE.search(b.text) and not stem_text.startswith(b.text.strip()):
            pass
        else:
            stem_blocks.append(b)

    return stem_blocks, options


def _detect_question_kind(stem_text: str, options: list[Option]) -> QuestionKind:
    """Determine question type from content patterns."""
    lower = stem_text.lower()

    if "more than one" in lower or "one or more" in lower:
        return QuestionKind.MCQ_MULTI

    if "passage" in lower or "comprehension" in lower or "paragraph" in lower:
        return QuestionKind.PASSAGE

    if "match the column" in lower or "match the following" in lower:
        return QuestionKind.MATCH

    if "assertion" in lower and "reason" in lower:
        return QuestionKind.ASSERTION

    if "numerical value" in lower or "integer" in lower or "decimal" in lower or len(options) == 0:
        return QuestionKind.NUMERIC

    if len(options) == 4:
        return QuestionKind.MCQ_SINGLE

    return QuestionKind.MCQ_SINGLE


def _check_numbering_continuity(questions: list[Question]) -> list[Issue]:
    """Check that question numbers form a continuous sequence 1..N.

    Returns issues for gaps and duplicates.
    """
    issues: list[Issue] = []
    if not questions:
        return issues

    seen_numbers: set[int] = set()
    for q in questions:
        if q.number in seen_numbers:
            issues.append(
                Issue(
                    id=f"s4_dup_q{q.number}",
                    stage="s4_structure",
                    severity=IssueSeverity.WARNING,
                    message=f"Duplicate question number {q.number} detected.",
                )
            )
        seen_numbers.add(q.number)

    sorted_numbers = sorted(list(seen_numbers))
    if not sorted_numbers:
        return issues

    min_num = sorted_numbers[0]
    max_num = sorted_numbers[-1]

    # Check for gaps between min_num and max_num
    full_range = set(range(min_num, max_num + 1))
    missing = sorted(list(full_range - seen_numbers))

    for m in missing:
        issues.append(
            Issue(
                id=f"s4_gap_q{m}",
                stage="s4_structure",
                severity=IssueSeverity.WARNING,
                message=f"Question {m} not found -- possible OCR or segmentation error",
            )
        )

    return issues
