"""Targeted gap re-search for Rule R14 missing question numbers."""

from __future__ import annotations

import logging
import re

from examforge.ir.schema import ExamDocument, Option, Question, QuestionKind

logger = logging.getLogger(__name__)

_OPT_RE = re.compile(r"(?:^|\n)\s*\(([A-Za-z0-9])\)\s*(.+)")


def gap_search_recover_question(
    doc: ExamDocument,
    missing_number: int,
) -> Question | None:
    """
    Search for a missing question number in the spatial gap between neighbors.

    Runs locally at T0/T1 before invoking any remote AI models.
    """
    questions = sorted(doc.questions, key=lambda q: q.number)
    if not questions:
        return None

    # Find neighbor questions
    prev_q = max(
        (q for q in questions if q.number < missing_number),
        default=None,
        key=lambda q: q.number,
    )
    next_q = min(
        (q for q in questions if q.number > missing_number),
        default=None,
        key=lambda q: q.number,
    )

    target_page = prev_q.source_pages[0] if (prev_q and prev_q.source_pages) else (
        next_q.source_pages[0] if (next_q and next_q.source_pages) else 1
    )

    # Search for blocks on target_page containing the missing number prefix
    prefix_pattern = re.compile(
        rf"(?:^|\n)\s*(?:Q\.?\s*|Question\s*|प्र\.?\s*)?{missing_number}\s*[-:.)]\s*(.+)",
        re.IGNORECASE,
    )

    candidate_blocks = [b for b in doc.blocks if b.page == target_page]
    for b in candidate_blocks:
        m = prefix_pattern.search(b.text)
        if m:
            full_text = b.text.strip()
            # Extract options
            opts: list[Option] = []
            opt_matches = list(_OPT_RE.finditer(full_text))
            if opt_matches:
                stem_end = opt_matches[0].start()
                raw_stem = full_text[:stem_end].strip()
                # Remove number prefix from stem if present
                clean_stem = prefix_pattern.sub(r"\1", raw_stem).strip()

                for opt_m in opt_matches:
                    lbl = opt_m.group(1).upper()
                    txt = opt_m.group(2).strip()
                    opts.append(Option(label=lbl, text_str_en=txt))
            else:
                clean_stem = prefix_pattern.sub(r"\1", full_text).strip()

            q = Question(
                id=f"q{missing_number}",
                number=missing_number,
                kind=QuestionKind.SINGLE_CORRECT if opts else QuestionKind.SHORT_ANSWER,
                stem_text_en=clean_stem,
                options=opts,
                source_pages=[target_page],
            )
            logger.info(
                "  GapSearch recovered missing question Q%d on page %d",
                missing_number,
                target_page,
            )
            return q

    return None
