"""
Language layout strategies and bilingual alignment for ExamForge v2 (Phase 6.3).

Implements all four language layouts:
1. parallel_columns (English left | Hindi right)
2. interleaved (EN then HI inside one column per question)
3. separate_sections (Full English booklet then Hindi booklet, aligned by question number)
4. monolingual (single language document)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from examforge.ir.schema import Block, Issue, IssueSeverity, Lang
from examforge.stages.s5_hindi import contains_devanagari, split_bilingual_text

logger = logging.getLogger(__name__)

LanguageLayout = Literal["monolingual", "parallel_columns", "interleaved", "separate_sections"]


@dataclass
class AlignedBilingualQuestion:
    """A question with aligned primary and secondary language streams."""

    number: int
    primary_text: str
    secondary_text: str = ""
    primary_blocks: list[Block] = field(default_factory=list)
    secondary_blocks: list[Block] = field(default_factory=list)


def align_language_layout(
    blocks: list[Block],
    layout_mode: LanguageLayout = "monolingual",
    primary_lang: str = "en",
    secondary_lang: str = "hi",
    page_width: float = 600.0,
) -> tuple[list[AlignedBilingualQuestion], list[Issue]]:
    """
    Align blocks into questions according to the specified language layout strategy.

    Emits an Issue when language question counts mismatch in bilingual modes.
    """
    issues: list[Issue] = []
    if not blocks:
        return [], issues

    if layout_mode == "monolingual":
        return _align_monolingual(blocks), issues

    if layout_mode == "parallel_columns":
        return _align_parallel_columns(blocks, page_width, issues)

    if layout_mode == "interleaved":
        return _align_interleaved(blocks), issues

    if layout_mode == "separate_sections":
        return _align_separate_sections(blocks, issues)

    # Fallback to monolingual
    return _align_monolingual(blocks), issues


def _extract_question_map(blocks: list[Block]) -> dict[int, tuple[str, list[Block]]]:
    """Segment blocks into a map of question_number -> (text, blocks)."""
    q_map: dict[int, tuple[str, list[Block]]] = {}
    curr_num = None
    curr_blocks: list[Block] = []

    pat = re.compile(r"^\s*(?:Q\.?\s*|प्र(?:श्न)?\.?\s*)?(\d{1,3})\s*[.):]", re.MULTILINE)

    for b in blocks:
        text = b.text.strip()
        m = pat.search(text)
        if m:
            num = int(m.group(1))
            if curr_num is not None:
                combined_txt = "\n".join(blk.text.strip() for blk in curr_blocks)
                q_map[curr_num] = (combined_txt, list(curr_blocks))
            curr_num = num
            curr_blocks = [b]
        else:
            if curr_num is not None:
                curr_blocks.append(b)

    if curr_num is not None and curr_blocks:
        combined_txt = "\n".join(blk.text.strip() for blk in curr_blocks)
        q_map[curr_num] = (combined_txt, list(curr_blocks))

    return q_map


def _align_monolingual(blocks: list[Block]) -> list[AlignedBilingualQuestion]:
    """Single language layout."""
    q_map = _extract_question_map(blocks)
    aligned: list[AlignedBilingualQuestion] = []
    for num in sorted(q_map.keys()):
        txt, blks = q_map[num]
        aligned.append(
            AlignedBilingualQuestion(
                number=num,
                primary_text=txt,
                secondary_text="",
                primary_blocks=blks,
            )
        )
    return aligned


def _align_parallel_columns(
    blocks: list[Block],
    page_width: float,
    issues: list[Issue],
) -> tuple[list[AlignedBilingualQuestion], list[Issue]]:
    """Parallel dual columns (e.g. Left English, Right Hindi)."""
    mid_x = page_width / 2.0
    left_blocks = [b for b in blocks if (b.bbox.x1 + b.bbox.x2) / 2.0 < mid_x]
    right_blocks = [b for b in blocks if (b.bbox.x1 + b.bbox.x2) / 2.0 >= mid_x]

    # Sort each column top to bottom
    left_blocks.sort(key=lambda b: (b.page, b.bbox.y1, b.bbox.x1))
    right_blocks.sort(key=lambda b: (b.page, b.bbox.y1, b.bbox.x1))

    left_map = _extract_question_map(left_blocks)
    right_map = _extract_question_map(right_blocks)

    if len(left_map) != len(right_map):
        issues.append(
            Issue(
                id="layout_parallel_count_mismatch",
                stage="s4_structure",
                severity=IssueSeverity.WARNING,
                message=(
                    f"Language alignment count mismatch: primary side has {len(left_map)} questions, "
                    f"secondary side has {len(right_map)} questions."
                ),
            )
        )

    all_nums = sorted(list(set(left_map.keys()).union(right_map.keys())))
    aligned: list[AlignedBilingualQuestion] = []

    for num in all_nums:
        prim_txt, prim_blks = left_map.get(num, ("", []))
        sec_txt, sec_blks = right_map.get(num, ("", []))
        aligned.append(
            AlignedBilingualQuestion(
                number=num,
                primary_text=prim_txt,
                secondary_text=sec_txt,
                primary_blocks=prim_blks,
                secondary_blocks=sec_blks,
            )
        )

    return aligned, issues


def _align_interleaved(blocks: list[Block]) -> list[AlignedBilingualQuestion]:
    """Interleaved language streams inside single question blocks."""
    q_map = _extract_question_map(blocks)
    aligned: list[AlignedBilingualQuestion] = []

    for num in sorted(q_map.keys()):
        txt, blks = q_map[num]
        en_txt, hi_txt = split_bilingual_text(txt)
        aligned.append(
            AlignedBilingualQuestion(
                number=num,
                primary_text=en_txt,
                secondary_text=hi_txt,
                primary_blocks=blks,
                secondary_blocks=blks if hi_txt else [],
            )
        )

    return aligned


def _align_separate_sections(
    blocks: list[Block],
    issues: list[Issue],
) -> tuple[list[AlignedBilingualQuestion], list[Issue]]:
    """Full English section followed by full Hindi section."""
    prim_blocks = [b for b in blocks if not contains_devanagari(b.text)]
    sec_blocks = [b for b in blocks if contains_devanagari(b.text)]

    prim_map = _extract_question_map(prim_blocks)
    sec_map = _extract_question_map(sec_blocks)

    if len(prim_map) != len(sec_map):
        issues.append(
            Issue(
                id="layout_sections_count_mismatch",
                stage="s4_structure",
                severity=IssueSeverity.WARNING,
                message=(
                    f"Language alignment count mismatch: primary section has {len(prim_map)} questions, "
                    f"secondary section has {len(sec_map)} questions."
                ),
            )
        )

    all_nums = sorted(list(set(prim_map.keys()).union(sec_map.keys())))
    aligned: list[AlignedBilingualQuestion] = []

    for num in all_nums:
        prim_txt, prim_blks = prim_map.get(num, ("", []))
        sec_txt, sec_blks = sec_map.get(num, ("", []))
        aligned.append(
            AlignedBilingualQuestion(
                number=num,
                primary_text=prim_txt,
                secondary_text=sec_txt,
                primary_blocks=prim_blks,
                secondary_blocks=sec_blks,
            )
        )

    return aligned, issues
