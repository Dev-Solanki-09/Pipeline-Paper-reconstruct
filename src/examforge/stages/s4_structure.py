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

from examforge.ir.schema import (
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    Issue,
    IssueSeverity,
    Option,
    PageClassification,
    PageInfo,
    Passage,
    Question,
    QuestionKind,
    TextNode,
)
from examforge.layout import (
    NumberingEngine,
    classify_question_kind,
    detect_internal_choice,
    detect_passages,
    is_valid_monotonic_step,
    link_questions_to_passages,
    order_blocks,
    parse_options_from_text,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Question number boundary patterns
PATTERN_DOT = re.compile(r"^\s*(\d{1,3})\s*[.):]", re.MULTILINE)
PATTERN_Q_DOT = re.compile(r"^\s*Q\.?\s*(\d{1,3})\s*[.):]?", re.IGNORECASE | re.MULTILINE)
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

# Option patterns - Line-anchored (preferred) and inline fallbacks
LINE_OPTION_ALPHA_RE = re.compile(r"(?:^|\n)\s*\(([A-D])\)\s*")
LINE_OPTION_LOWER_RE = re.compile(r"(?:^|\n)\s*\(([a-d])\)\s*")
LINE_OPTION_NUM_RE = re.compile(r"(?:^|\n)\s*\(([1-4])\)\s*")

OPTION_ALPHA_RE = re.compile(r"(?:^|[\s\n])\(([A-D])\)\s*", re.MULTILINE)
OPTION_LOWER_RE = re.compile(r"(?:^|[\s\n])\(([a-d])\)\s*", re.MULTILINE)
OPTION_NUM_RE = re.compile(r"(?:^|[\s\n])\(([1-4])\)\s*", re.MULTILINE)

# Preceding words that indicate parenthesized numbers are prose references, not options
PROSE_PREFIX_RE = re.compile(
    r"(?:Statement|Equation|Reaction|Case|Condition|Step|Figure|Fig|Part)\s*[-–:]?\s*$",
    re.IGNORECASE,
)


@dataclass
class RawQuestion:
    """Intermediate representation before creating Question objects."""

    number: int
    stem_blocks: list[Block] = field(default_factory=list)
    option_blocks: dict[str, list[Block]] = field(default_factory=dict)
    stem_text: str = ""
    options_text: dict[str, str] = field(default_factory=dict)
    source_pages: list[int] = field(default_factory=list)
    section: str | None = None


class S4Structure(Stage):
    """
    Stage 4: Segment text blocks into structured Question objects.
    """

    name = "s4_structure"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["column_sort", "structure_detection", "question_segmentation"]

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
            p.page_number for p in doc.pages if p.classification == PageClassification.QUESTIONS
        }

        # If no pages classified as QUESTIONS, check for any non-cover, non-rough pages
        if not question_page_numbers:
            question_page_numbers = {
                p.page_number
                for p in doc.pages
                if p.classification
                not in (
                    PageClassification.COVER,
                    PageClassification.ROUGH_WORK,
                    PageClassification.BLANK,
                )
            }

        candidate_blocks = [
            b
            for b in doc.blocks
            if b.page in question_page_numbers and b.status != BlockStatus.DROPPED
        ]

        use_layout_v2 = (
            ctx.config.flag("layout_v2", default=True)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else True
        )

        # 2. Sort blocks in true document reading order
        if use_layout_v2:
            page_info_map = {p.page_number: p for p in doc.pages}
            blocks_by_page: dict[int, list[Block]] = {}
            for b in candidate_blocks:
                blocks_by_page.setdefault(b.page, []).append(b)

            strategy = (
                ctx.resolved_profile.layout.reading_order
                if (ctx.resolved_profile and ctx.resolved_profile.layout)
                else "columns_ltr"
            )
            direction = (
                ctx.resolved_profile.language.direction
                if (
                    ctx.resolved_profile
                    and hasattr(ctx.resolved_profile, "language")
                    and ctx.resolved_profile.language
                )
                else "ltr"
            )

            sorted_blocks: list[Block] = []
            for page_num in sorted(blocks_by_page.keys()):
                p_blocks = blocks_by_page[page_num]
                p_info = page_info_map.get(page_num)
                page_w = (
                    float(p_info.width_px)
                    if (p_info and p_info.width_px > 0)
                    else max((b.bbox.x2 for b in p_blocks), default=595.0)
                )
                page_h = (
                    float(p_info.height_px)
                    if (p_info and p_info.height_px > 0)
                    else max((b.bbox.y2 for b in p_blocks), default=842.0)
                )
                sorted_blocks.extend(
                    order_blocks(p_blocks, page_w, page_h, strategy=strategy, direction=direction)
                )
            candidate_blocks = sorted_blocks
        else:
            candidate_blocks = _sort_blocks_reading_order(candidate_blocks, doc.pages)

        if not candidate_blocks:
            logger.warning("S4Structure: No candidate blocks found for segmentation.")
            return StageResult(document=doc, metrics={"questions_extracted": 0}, issues=issues)

        # 3. Find profile expectations
        custom_patterns = (
            ctx.resolved_profile.numbering.patterns
            if ctx.resolved_profile and ctx.resolved_profile.numbering
            else []
        )
        custom_sections = (
            ctx.resolved_profile.numbering.sections
            if ctx.resolved_profile and ctx.resolved_profile.numbering
            else []
        )
        custom_labels = (
            ctx.resolved_profile.options.label_schemes
            if ctx.resolved_profile and ctx.resolved_profile.options
            else None
        )

        q_passage_links: dict[int, str] = {}
        if use_layout_v2:
            detected_passages = detect_passages(candidate_blocks)
            engine = NumberingEngine(
                patterns=custom_patterns,
                sections=custom_sections,
                label_schemes=custom_labels,
            )
            raw_questions = _segment_questions_v2(candidate_blocks, engine)

            if detected_passages:
                q_passage_links = link_questions_to_passages(
                    detected_passages,
                    [rq.number for rq in raw_questions],
                )
                if not doc.passages:
                    doc.passages = [
                        Passage(
                            id=p.passage_id,
                            nodes=[TextNode(texts={"en": p.text})],
                            question_refs=[f"q{q}" for q in p.target_questions],
                        )
                        for p in detected_passages
                    ]
        else:
            all_text = "\n".join(b.text for b in candidate_blocks)
            pattern = _find_question_pattern(all_text, custom_patterns)
            if pattern is None:
                pattern = PATTERN_DOT
            raw_questions = _segment_questions(candidate_blocks, pattern, custom_sections)

        # 4. Convert RawQuestion to Question IR objects
        questions: list[Question] = []
        for idx, rq in enumerate(raw_questions, start=1):
            if use_layout_v2:
                stem_text, options = parse_options_from_text(rq.stem_text, schemes=custom_labels)
                if not options:
                    stem_text, options = _parse_options_from_raw(rq)
                pid = q_passage_links.get(rq.number)
                kind = classify_question_kind(stem_text, options, has_passage=bool(pid))
                alt_choices = detect_internal_choice(stem_text)
                choice_grp = f"cg_{rq.number}" if len(alt_choices) >= 2 else None
            else:
                stem_text, options = _parse_options_from_raw(rq)
                kind = _detect_question_kind(stem_text, options)
                pid = None
                choice_grp = None

            q = Question(
                id=f"q{rq.number}",
                number=rq.number,
                original_number=rq.number,
                sequence_index=idx,
                section=rq.section,
                kind=kind,
                stem_en=rq.stem_blocks,
                stem_text_en=stem_text,
                options=options,
                choice_group=choice_grp,
                passage_ref=pid,
                source_pages=sorted(list(set(rq.source_pages))),
            )
            questions.append(q)

        # 5. Check numbering continuity
        continuity_issues = _check_numbering_continuity(questions)
        issues.extend(continuity_issues)

        # Save questions to document
        doc.questions = questions

        # Phase 10: Extract and bind answers, marking schemes, and solutions if answers flag is enabled
        use_answers = (
            ctx.config.flag("answers", default=False)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else False
        )
        if use_answers:
            _bind_answers_and_solutions_stage(doc, ctx)

        # Phase 12: Check Question Bank reuse if bank flag is enabled
        use_bank = (
            ctx.config.flag("bank", default=False)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else False
        )
        if use_bank:
            _apply_bank_reuse(doc, ctx)

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


def _find_question_pattern(
    text: str,
    custom_patterns: list[str] | None = None,
) -> re.Pattern | None:
    """Try multiple question-number patterns and return the best match.

    Returns the pattern matching >= 5 times, or the most frequent if none reach 5.
    Returns None if no patterns match.
    """
    candidates = []
    if custom_patterns:
        for p in custom_patterns:
            try:
                candidates.append((re.compile(p, re.MULTILINE), p))
            except re.error:
                pass
    if not candidates:
        candidates = CANDIDATE_PATTERNS

    best_pattern = None
    max_count = 0

    for pat, _ in candidates:
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


def _sort_blocks_reading_order(blocks: list[Block], pages: list[PageInfo]) -> list[Block]:
    """Sort blocks in true document reading order.

    For 2-column pages (common in JEE/NEET papers), blocks must be processed
    column-by-column: full-width headers -> left column (top-to-bottom) ->
    right column (top-to-bottom) -> full-width footers.

    For single-column pages, blocks are sorted purely top-to-bottom.
    """
    page_info_map = {p.page_number: p for p in pages}

    blocks_by_page: dict[int, list[Block]] = {}
    for b in blocks:
        blocks_by_page.setdefault(b.page, []).append(b)

    sorted_blocks: list[Block] = []

    for page_num in sorted(blocks_by_page.keys()):
        p_blocks = blocks_by_page[page_num]
        p_info = page_info_map.get(page_num)

        page_width = (
            float(p_info.width_px)
            if (p_info and p_info.width_px > 0)
            else max((b.bbox.x2 for b in p_blocks), default=595.0)
        )
        page_height = (
            float(p_info.height_px)
            if (p_info and p_info.height_px > 0)
            else max((b.bbox.y2 for b in p_blocks), default=842.0)
        )

        is_two_col = (p_info.column_count == 2) if p_info else False
        if not is_two_col and len(p_blocks) >= 4:
            mid_x = page_width / 2.0
            left_col = sum(
                1 for b in p_blocks if b.bbox.x2 <= mid_x * 1.05 and b.bbox.width < page_width * 0.7
            )
            right_col = sum(
                1 for b in p_blocks if b.bbox.x1 >= mid_x * 0.95 and b.bbox.width < page_width * 0.7
            )
            if left_col >= 2 and right_col >= 2:
                is_two_col = True

        if not is_two_col:
            p_blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))
        else:
            mid_x = page_width / 2.0

            def _col_key(b: Block) -> tuple[int, int, int]:
                is_full_width = b.bbox.width > page_width * 0.65
                if is_full_width and b.bbox.y1 < page_height * 0.20:
                    return (0, b.bbox.y1, b.bbox.x1)
                elif is_full_width and b.bbox.y2 > page_height * 0.85:
                    return (3, b.bbox.y1, b.bbox.x1)
                else:
                    center_x = (b.bbox.x1 + b.bbox.x2) / 2.0
                    col = 1 if center_x < mid_x else 2
                    return (col, b.bbox.y1, b.bbox.x1)

            p_blocks.sort(key=_col_key)

        sorted_blocks.extend(p_blocks)

    return sorted_blocks


def _is_valid_new_question_start(
    num: int,
    text: str,
    current_rq: RawQuestion | None,
    current_section: str | None,
) -> bool:
    """Validate whether a numbered block represents a genuine question start."""
    # Never treat an option block (e.g. starting with "(A)" or "(1)") as a question
    if re.match(r"^\s*\(([A-Da-d1-4])\)", text):
        return False

    # First question can start at 1 or any valid initial offset (e.g. Q26)
    if current_rq is None:
        return num > 0

    # Normal monotonic sequence progression (next question or small gap <= 5)
    if current_rq.number < num <= current_rq.number + 5:
        return True

    # Section restarted numbering from 1
    if num == 1 and (current_section != current_rq.section or current_rq.number >= 10):
        return True

    # Otherwise, it's a chemical equation (e.g. "2. SO3"), table row, or itemized sub-point
    return False


def _segment_questions(
    blocks: list[Block],
    pattern: re.Pattern,
    custom_sections: list[str] | None = None,
) -> list[RawQuestion]:
    """Split a sorted block stream into raw question segments."""
    raw_questions: list[RawQuestion] = []
    current_section: str | None = None
    current_rq: RawQuestion | None = None

    section_re = SECTION_RE
    if custom_sections:
        try:
            section_re = re.compile("|".join(custom_sections), re.IGNORECASE)
        except re.error:
            section_re = SECTION_RE

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        # Check if block is a section header (from Paddle-VL layout tag or regex)
        if block.type == BlockType.HEADER or (
            len(text) < 80 and section_re.search(text) and not pattern.match(text)
        ):
            current_section = text
            continue

        # Check if block starts a new question
        match = pattern.match(text)
        is_new_q = False
        num = None
        if match:
            try:
                num = int(match.group(1))
            except (ValueError, IndexError):
                num = len(raw_questions) + 1

            if _is_valid_new_question_start(num, text, current_rq, current_section):
                is_new_q = True

        if is_new_q and match and num is not None:
            # Save previous question if exists
            if current_rq is not None:
                raw_questions.append(current_rq)

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


def _segment_questions_v2(
    blocks: list[Block],
    engine: NumberingEngine,
) -> list[RawQuestion]:
    """Segment a sorted block stream using NumberingEngine with monotonicity and chemical formula guards."""
    raw_questions: list[RawQuestion] = []
    current_section: str | None = None
    current_rq: RawQuestion | None = None

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue

        if block.type == BlockType.HEADER or engine.is_section_header(text):
            current_section = text
            continue

        q_start = engine.match_question_start(text)
        is_new_q = False
        num = None

        if q_start is not None:
            num = q_start.number
            curr_num = current_rq.number if current_rq else None
            curr_sec = current_rq.section if current_rq else None
            if is_valid_monotonic_step(curr_num, num, curr_sec, current_section):
                is_new_q = True

        if is_new_q and q_start is not None and num is not None:
            if current_rq is not None:
                raw_questions.append(current_rq)

            stem_remainder = text[q_start.prefix_length :].strip()
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

    # 1. Try line-anchored matches first (options start at newline or beginning)
    alpha_matches = list(LINE_OPTION_ALPHA_RE.finditer(full_text))
    lower_matches = list(LINE_OPTION_LOWER_RE.finditer(full_text))
    num_matches = list(LINE_OPTION_NUM_RE.finditer(full_text))

    chosen_matches = []
    if len(alpha_matches) >= 2:
        chosen_matches = alpha_matches
    elif len(lower_matches) >= 2:
        chosen_matches = lower_matches
    elif len(num_matches) >= 2:
        chosen_matches = num_matches
    else:
        # Fallback to inline matches, but filter out matches preceded by prose keywords
        def _filter_prose(matches: list[re.Match]) -> list[re.Match]:
            filtered = []
            for m in matches:
                prefix = full_text[: m.start()]
                if not PROSE_PREFIX_RE.search(prefix):
                    filtered.append(m)
            return filtered

        inline_alpha = _filter_prose(list(OPTION_ALPHA_RE.finditer(full_text)))
        inline_lower = _filter_prose(list(OPTION_LOWER_RE.finditer(full_text)))
        inline_num = _filter_prose(list(OPTION_NUM_RE.finditer(full_text)))

        if len(inline_alpha) >= 2:
            chosen_matches = inline_alpha
        elif len(inline_lower) >= 2:
            chosen_matches = inline_lower
        elif len(inline_num) >= 2:
            chosen_matches = inline_num

    if not chosen_matches:
        # No options detected -> all text is stem
        stem = re.sub(
            r"SPACE FOR ROUGH WORK.*$", "", full_text, flags=re.IGNORECASE | re.DOTALL
        ).strip()
        return stem, []

    # If there are extraneous matches from earlier in the question stem, keep the final sequential group
    if len(chosen_matches) > 4:
        cur_run = [chosen_matches[-1]]
        for m in reversed(chosen_matches[:-1]):
            cur_label = cur_run[0].group(1).upper()
            prev_label = m.group(1).upper()
            if (prev_label < cur_label) or (prev_label == "4" and cur_label == "1"):
                cur_run.insert(0, m)
            else:
                break
        if len(cur_run) >= 2:
            chosen_matches = cur_run

    # Stem is everything before the first option
    first_opt = chosen_matches[0]
    stem = full_text[: first_opt.start()].strip()
    stem = re.sub(r"SPACE FOR ROUGH WORK.*$", "", stem, flags=re.IGNORECASE | re.DOTALL).strip()

    options: list[Option] = []
    for i, match in enumerate(chosen_matches):
        label = match.group(1).upper()
        start = match.end()
        end = chosen_matches[i + 1].start() if i + 1 < len(chosen_matches) else len(full_text)
        opt_text = full_text[start:end].strip()

        opt_text = re.sub(
            r"SPACE FOR ROUGH WORK.*$", "", opt_text, flags=re.IGNORECASE | re.DOTALL
        ).strip()
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
    stem_text, options = _parse_options_from_raw(
        RawQuestion(number=1, stem_text=full_text, stem_blocks=blocks)
    )

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


def get_option_packing_class(options: Any) -> str:
    """Determine intelligent greedy packing layout for options based on content length.

    - opt-grid-4: 4 options, all compact (<= 14 characters) -> single row / 4-column packing
    - opt-grid-2: 2 or 4 options, medium length (<= 32 characters) -> 2x2 grid packing
    - opt-col-1: standard vertical stacked column for longer text / multi-line formulas
    """
    if hasattr(options, "options"):
        options = options.options
    elif isinstance(options, dict) and "options" in options:
        options = options["options"]

    if not options or not isinstance(options, (list, tuple)):
        return "opt-col-1"

    # Strip HTML tags, embedded images, and base64 payloads to evaluate true visible typographic length
    texts = []
    has_image = False
    for opt in options:
        raw = getattr(opt, "text_str_en", None) or getattr(opt, "text_str_hi", None) or ""
        if "<img" in raw or "data:image" in raw or ".png" in raw or ".jpg" in raw:
            has_image = True
        # Strip long base64 data URIs before stripping tags
        clean = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "", raw)
        clean = re.sub(r"<[^>]+>", "", clean).strip()
        texts.append(clean)

    if has_image:
        return "opt-col-1"

    max_len = max((len(t) for t in texts), default=0)

    if len(options) == 4:
        if max_len <= 14:
            return "opt-grid-4"
        elif max_len <= 32:
            return "opt-grid-2"
        return "opt-col-1"
    elif len(options) == 2:
        if max_len <= 32:
            return "opt-grid-2"
        return "opt-col-1"

    return "opt-col-1"


def _bind_answers_and_solutions_stage(doc: ExamDocument, ctx: StageContext) -> None:
    """Helper to detect and bind answer keys, marking schemes, and solutions when answers flag is enabled."""
    from examforge.answers.bind import bind_answers
    from examforge.answers.marks import (
        apply_marking_schemes,
        parse_marking_scheme,
        parse_section_marking_schemes,
    )
    from examforge.answers.parse_key import (
        parse_answer_key_grid,
        parse_answer_key_inline,
        parse_answer_key_table,
        parse_answer_key_text,
    )
    from examforge.answers.solutions import bind_solutions, parse_solution_blocks

    # 1. Answer key pages
    key_pages = {
        p.page_number for p in doc.pages if p.classification == PageClassification.ANSWER_KEY
    }
    if key_pages:
        key_blocks = [
            b for b in doc.blocks if b.page in key_pages and b.status != BlockStatus.DROPPED
        ]
        if key_blocks:
            key_text = "\n".join(b.text for b in key_blocks)
            entries = parse_answer_key_text(key_text)
            if not entries:
                entries = parse_answer_key_grid(key_text)
            if not entries:
                entries = parse_answer_key_inline(key_text)
            if entries:
                bind_answers(doc, entries, ctx.resolved_profile)

    # 2. Answer key tables
    if hasattr(doc, "tables") and doc.tables:
        for t in doc.tables:
            if t.rows:
                str_rows = [[cell.text for cell in row] for row in t.rows]
                t_entries = parse_answer_key_table(str_rows)
                if t_entries:
                    bind_answers(doc, t_entries, ctx.resolved_profile)

    # 3. Inline answer keys in question stems (if still unbound)
    if not any(q.answer is not None for q in doc.questions):
        combined_stem_text = "\n".join(
            f"Question {q.number}:\n{q.stem_text_en}" for q in doc.questions
        )
        inline_entries = parse_answer_key_inline(combined_stem_text)
        if inline_entries:
            bind_answers(doc, inline_entries, ctx.resolved_profile)

    # 4. Marking schemes from instruction pages
    instr_pages = {
        p.page_number
        for p in doc.pages
        if p.classification in (PageClassification.INSTRUCTIONS, PageClassification.COVER)
    }
    if instr_pages:
        instr_blocks = [
            b for b in doc.blocks if b.page in instr_pages and b.status != BlockStatus.DROPPED
        ]
        if instr_blocks:
            instr_text = "\n".join(b.text for b in instr_blocks)
            sec_schemes = parse_section_marking_schemes(instr_text)
            default_scheme = parse_marking_scheme(instr_text)
            apply_marking_schemes(doc, default_marks=default_scheme, section_marks=sec_schemes)

    # 5. Solutions in document blocks
    all_text = "\n".join(b.text for b in doc.blocks if b.status != BlockStatus.DROPPED)
    sol_blocks = parse_solution_blocks(all_text)
    if sol_blocks:
        bind_solutions(doc, sol_blocks)


def _apply_bank_reuse(doc: ExamDocument, ctx: StageContext) -> None:
    """Check Question Bank and apply exact 0-token reuse when bank flag is enabled."""
    from pathlib import Path

    from examforge.bank.match import MatchKind, QuestionBankMatcher
    from examforge.bank.store import QuestionBankStore
    from examforge.ir.schema import Provenance

    bank_path = getattr(ctx.config, "bank_path", Path("data/bank/bank.db"))
    if not Path(bank_path).exists():
        return

    store = QuestionBankStore(bank_path)
    matcher = QuestionBankMatcher(store)
    family = (
        ctx.resolved_profile.id
        if (ctx.resolved_profile and hasattr(ctx.resolved_profile, "id"))
        else None
    )

    reused_count = 0
    for q in doc.questions:
        res = matcher.match(q, exam_family=family)
        if res.kind == MatchKind.EXACT_REUSE:
            q.provenance = Provenance.BANK
            q.confidence = 1.0
            reused_count += 1
        elif res.kind == MatchKind.NEAR_HINT:
            doc.issues.append(
                Issue(
                    id=f"bank_discrepancy_q{q.number}",
                    stage="s4_structure",
                    rule="bank",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Question Q{q.number} matches bank question but has differing "
                        f"numerals/units"
                    ),
                    evidence=res.evidence,
                )
            )

    if reused_count:
        logger.info("  QuestionBank: %d question(s) reused from verified bank", reused_count)
