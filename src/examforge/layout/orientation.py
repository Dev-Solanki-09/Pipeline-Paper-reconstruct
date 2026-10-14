"""
Page orientation and two-up spread detection and handling for ExamForge v2 (Phase 6.9).

Handles landscape vs portrait detection and splits two-up booklet spreads at the central gutter.
"""

from __future__ import annotations

import logging
from typing import Sequence

from examforge.ir.schema import BBox, Block

logger = logging.getLogger(__name__)


def detect_page_orientation(
    page_width: float,
    page_height: float,
    blocks: Sequence[Block] = (),
) -> str:
    """
    Detect whether a page is portrait or landscape from geometric dimensions and block layout.

    Returns 'portrait' or 'landscape'.
    """
    if page_width > page_height * 1.15:
        return "landscape"
    return "portrait"


def detect_two_up_spread(
    page_width: float,
    page_height: float,
    blocks: Sequence[Block] = (),
) -> bool:
    """
    Detect whether a landscape page is a two-up spread (two portrait pages scanned side-by-side).
    """
    # Requires landscape aspect ratio >= 1.25
    if page_width < page_height * 1.20:
        return False

    if not blocks:
        return True

    # Check for gutter near the center (x in 45%..55%)
    mid_start = page_width * 0.46
    mid_end = page_width * 0.54

    crossing_blocks = sum(1 for b in blocks if b.bbox.x1 < mid_start and b.bbox.x2 > mid_end)
    left_blocks = sum(1 for b in blocks if b.bbox.x2 <= mid_start)
    right_blocks = sum(1 for b in blocks if b.bbox.x1 >= mid_end)

    if left_blocks >= 2 and right_blocks >= 2 and crossing_blocks <= 1:
        return True

    return False


def split_two_up_blocks(
    blocks: Sequence[Block],
    page_width: float,
) -> tuple[list[Block], list[Block]]:
    """
    Split blocks of a two-up spread into left-page blocks and right-page blocks.

    Returns (left_blocks, right_blocks).
    """
    mid_x = page_width / 2.0
    left_blocks: list[Block] = []
    right_blocks: list[Block] = []

    for b in blocks:
        center_x = (b.bbox.x1 + b.bbox.x2) / 2.0
        if center_x < mid_x:
            left_blocks.append(b)
        else:
            right_blocks.append(b)

    return left_blocks, right_blocks
