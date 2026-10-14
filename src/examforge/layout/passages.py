"""
Passage and comprehension detection and question linking for ExamForge v2 (Phase 6.6).

Detects comprehension passage boundaries, question range targets, and links questions to Passages.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from examforge.ir.schema import Block

logger = logging.getLogger(__name__)

# Patterns matching passage introductions and question range indicators
_PASSAGE_RANGE_RE = re.compile(
    r"(?:Read\s+the\s+(?:following\s+)?(?:passage|comprehension|paragraph)|"
    r"Questions?\s*(?:No\.?)?\s*(\d{1,3})\s*(?:to|-|–|and)\s*(\d{1,3})\s*(?:are\s+based\s+on|refer\s+to))",
    re.IGNORECASE,
)

_RANGE_EXTRACT_RE = re.compile(
    r"Questions?\s*(?:No\.?)?\s*(\d{1,3})\s*(?:to|-|–)\s*(\d{1,3})",
    re.IGNORECASE,
)


@dataclass
class PassageSegment:
    """Detected passage block with linked question target numbers."""

    passage_id: str
    text: str
    target_questions: list[int] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)


def detect_passages(
    blocks: list[Block],
    profile_patterns: list[str] | None = None,
) -> list[PassageSegment]:
    """
    Detect comprehension passages and extract target question ranges.
    """
    passages: list[PassageSegment] = []
    if not blocks:
        return passages

    i = 0
    passage_counter = 1

    while i < len(blocks):
        block = blocks[i]
        text = block.text.strip()

        # Check if block matches passage introduction
        if _PASSAGE_RANGE_RE.search(text):
            range_match = _RANGE_EXTRACT_RE.search(text)
            target_qs: list[int] = []
            if range_match:
                start_q = int(range_match.group(1))
                end_q = int(range_match.group(2))
                if 0 < start_q <= end_q and end_q - start_q <= 15:
                    target_qs = list(range(start_q, end_q + 1))

            # Collect subsequent passage text blocks until a numbered question starts
            body_blocks: list[Block] = []
            pages = [block.page]
            j = i + 1

            while j < len(blocks):
                next_b = blocks[j]
                next_text = next_b.text.strip()
                # If next block starts a question in target_qs (e.g. "41. What..."), stop!
                if target_qs:
                    first_target = target_qs[0]
                    if re.match(rf"^\s*(?:Q\.?\s*)?{first_target}\s*[.):]", next_text):
                        break
                elif re.match(r"^\s*(\d{1,3})\s*[.):]", next_text):
                    break

                body_blocks.append(next_b)
                if next_b.page not in pages:
                    pages.append(next_b.page)
                j += 1

            passage_text = text
            if body_blocks:
                passage_text += "\n\n" + "\n\n".join(b.text.strip() for b in body_blocks)

            passages.append(
                PassageSegment(
                    passage_id=f"pass_{passage_counter}",
                    text=passage_text,
                    target_questions=target_qs,
                    source_pages=pages,
                )
            )
            passage_counter += 1
            i = j
        else:
            i += 1

    return passages


def link_questions_to_passages(
    passages: list[PassageSegment],
    question_numbers: list[int],
) -> dict[int, str]:
    """
    Map question numbers to their enclosing passage_id.

    Returns dict of question_number -> passage_id.
    """
    links: dict[int, str] = {}
    q_set = set(question_numbers)

    for p in passages:
        for q_num in p.target_questions:
            if q_num in q_set:
                links[q_num] = p.passage_id

    return links
