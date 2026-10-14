"""
Column detection and span classification for ExamForge v2 (Phase 6.1).

Uses vertical-whitespace projection over text and graphic ink occupancy to detect
1, 2, or 3+ columns, sustained gutters, and classifies crossing blocks as spans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from examforge.ir.schema import BBox, Block

logger = logging.getLogger(__name__)


class SpanType(str, Enum):
    TOP_BANNER = "top_banner"
    BOTTOM_BANNER = "bottom_banner"
    FULL_WIDTH_PASSAGE = "full_width_passage"
    WIDE_TABLE = "wide_table"
    UNKNOWN_SPAN = "unknown_span"


@dataclass
class ColumnSpan:
    """A block that spans across multiple column boundaries."""

    block: Block
    span_type: SpanType


@dataclass
class ColumnInfo:
    """Information and blocks for a single detected column."""

    index: int
    x1: float
    x2: float
    blocks: list[Block] = field(default_factory=list)


@dataclass
class ColumnLayout:
    """Complete multi-column layout for a page."""

    num_columns: int
    columns: list[ColumnInfo]
    spans: list[ColumnSpan] = field(default_factory=list)


def detect_columns(
    blocks: list[Block],
    page_width: float,
    page_height: float,
    expected_columns: int | Literal["auto"] = "auto",
    min_gutter_width: float = 12.0,
    span_width_ratio: float = 0.65,
) -> ColumnLayout:
    """
    Detect column structure and classify spans for a given set of page blocks.

    Args:
        blocks: List of IR blocks on the page.
        page_width: Width of the page in points.
        page_height: Height of the page in points.
        expected_columns: Expected column count from profile (1, 2, 3 or "auto").
        min_gutter_width: Minimum whitespace gap in points to qualify as a column gutter.
        span_width_ratio: Width fraction above which a block is considered a span.

    Returns:
        ColumnLayout containing columns and classified spans.
    """
    if not blocks:
        return ColumnLayout(
            num_columns=1 if expected_columns == "auto" else int(expected_columns),
            columns=[ColumnInfo(index=0, x1=0.0, x2=page_width, blocks=[])],
            spans=[],
        )

    spans: list[ColumnSpan] = []
    col_candidate_blocks: list[Block] = []

    # 1. First-pass span extraction (wide blocks spanning > ratio of page)
    for b in blocks:
        width = b.bbox.width
        if width >= page_width * span_width_ratio:
            # Classify span by vertical position and content
            text_lower = b.text.lower()
            if b.bbox.y1 < page_height * 0.18:
                stype = SpanType.TOP_BANNER
            elif b.bbox.y2 > page_height * 0.85:
                stype = SpanType.BOTTOM_BANNER
            elif "table" in text_lower or "|" in b.text:
                stype = SpanType.WIDE_TABLE
            else:
                stype = SpanType.FULL_WIDTH_PASSAGE
            spans.append(ColumnSpan(block=b, span_type=stype))
        else:
            col_candidate_blocks.append(b)

    # 2. Vertical-whitespace projection on column candidate blocks
    if not col_candidate_blocks:
        # All blocks on page span wide width -> single column page, no spans
        single_col = ColumnInfo(index=0, x1=0.0, x2=page_width, blocks=[s.block for s in spans])
        single_col.blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))
        return ColumnLayout(num_columns=1, columns=[single_col], spans=[])

    if expected_columns == 1 and len(col_candidate_blocks) < 4:
        all_blocks = list(col_candidate_blocks) + [s.block for s in spans]
        single_col = ColumnInfo(index=0, x1=0.0, x2=page_width, blocks=all_blocks)
        single_col.blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))
        return ColumnLayout(num_columns=1, columns=[single_col], spans=[])

    # Discretize width into 2pt bins
    bin_size = 2.0
    num_bins = max(1, int(page_width / bin_size))
    occupancy = [0.0] * num_bins

    for b in col_candidate_blocks:
        start_bin = max(0, int(b.bbox.x1 / bin_size))
        end_bin = min(num_bins, int(b.bbox.x2 / bin_size) + 1)
        h = b.bbox.height
        for i in range(start_bin, end_bin):
            occupancy[i] += h

    # Search for valleys between 20% and 80% of page width
    search_start = int(0.20 * num_bins)
    search_end = int(0.80 * num_bins)
    min_gutter_bins = int(min_gutter_width / bin_size)

    valleys: list[tuple[float, float]] = []
    in_valley = False
    valley_start = 0

    for i in range(search_start, search_end):
        is_empty = occupancy[i] < 1.0  # minimal or zero height occupancy
        if is_empty:
            if not in_valley:
                in_valley = True
                valley_start = i
        else:
            if in_valley:
                in_valley = False
                valley_len = i - valley_start
                if valley_len >= min_gutter_bins:
                    v_x1 = valley_start * bin_size
                    v_x2 = i * bin_size
                    valleys.append((v_x1, v_x2))

    if in_valley:
        valley_len = search_end - valley_start
        if valley_len >= min_gutter_bins:
            valleys.append((valley_start * bin_size, search_end * bin_size))

    # Determine column count
    num_cols = 1
    if expected_columns == "auto":
        if len(valleys) == 1:
            num_cols = 2
        elif len(valleys) >= 2:
            num_cols = min(3, len(valleys) + 1)
        else:
            # Check if blocks naturally separate into two halves
            mid_x = page_width / 2.0
            left_count = sum(1 for b in col_candidate_blocks if b.bbox.x2 <= mid_x * 1.08)
            right_count = sum(1 for b in col_candidate_blocks if b.bbox.x1 >= mid_x * 0.92)
            if left_count >= 2 and right_count >= 2:
                num_cols = 2
    else:
        num_cols = int(expected_columns)

    # If single column confirmed
    if num_cols <= 1:
        all_blocks = list(col_candidate_blocks) + [s.block for s in spans]
        single_col = ColumnInfo(index=0, x1=0.0, x2=page_width, blocks=all_blocks)
        single_col.blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))
        return ColumnLayout(num_columns=1, columns=[single_col], spans=[])

    # Build column boundaries
    columns: list[ColumnInfo] = []
    if num_cols == 2:
        gutter_mid = (valleys[0][0] + valleys[0][1]) / 2.0 if valleys else page_width / 2.0
        columns = [
            ColumnInfo(index=0, x1=0.0, x2=gutter_mid),
            ColumnInfo(index=1, x1=gutter_mid, x2=page_width),
        ]
    elif num_cols == 3:
        if len(valleys) >= 2:
            g1_mid = (valleys[0][0] + valleys[0][1]) / 2.0
            g2_mid = (valleys[1][0] + valleys[1][1]) / 2.0
        else:
            g1_mid = page_width / 3.0
            g2_mid = (2.0 * page_width) / 3.0
        columns = [
            ColumnInfo(index=0, x1=0.0, x2=g1_mid),
            ColumnInfo(index=1, x1=g1_mid, x2=g2_mid),
            ColumnInfo(index=2, x1=g2_mid, x2=page_width),
        ]
    else:
        # Fallback uniform splits
        step = page_width / num_cols
        for idx in range(num_cols):
            columns.append(ColumnInfo(index=idx, x1=idx * step, x2=(idx + 1) * step))

    # 3. Assign blocks to columns
    for b in col_candidate_blocks:
        center_x = (b.bbox.x1 + b.bbox.x2) / 2.0
        assigned = False
        for col in columns:
            if col.x1 <= center_x < col.x2:
                col.blocks.append(b)
                assigned = True
                break
        if not assigned:
            # Fallback to closest column
            closest_col = min(columns, key=lambda c: abs(center_x - (c.x1 + c.x2) / 2.0))
            closest_col.blocks.append(b)

    # Sort blocks within each column top-to-bottom
    for col in columns:
        col.blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))

    return ColumnLayout(num_columns=num_cols, columns=columns, spans=spans)
