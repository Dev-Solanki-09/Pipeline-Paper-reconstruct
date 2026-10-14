"""
Reading order determination for ExamForge v2 (Phase 6.2).

Implements recursive XY-cut and column-based reading order algorithms
(columns_ltr, columns_rtl, xy_cut, parallel) with span and RTL awareness.
"""

from __future__ import annotations

import logging
from typing import Literal

from examforge.ir.schema import BBox, Block
from examforge.layout.columns import SpanType, detect_columns

logger = logging.getLogger(__name__)

Strategy = Literal["columns_ltr", "columns_rtl", "xy_cut", "parallel"]


def order_blocks(
    blocks: list[Block],
    page_width: float,
    page_height: float,
    strategy: str = "columns_ltr",
    direction: str = "ltr",
) -> list[Block]:
    """
    Sort blocks in true document reading order according to the configured strategy.

    Args:
        blocks: List of IR blocks on the page.
        page_width: Width of the page in points.
        page_height: Height of the page in points.
        strategy: 'columns_ltr', 'columns_rtl', 'xy_cut', or 'parallel'.
        direction: 'ltr' or 'rtl'.

    Returns:
        Ordered list of blocks.
    """
    if not blocks:
        return []

    if len(blocks) == 1:
        return list(blocks)

    if strategy == "xy_cut":
        return _xy_cut_sort(blocks, direction=direction)

    if strategy in ("columns_ltr", "columns_rtl", "parallel"):
        return _columns_sort(
            blocks,
            page_width=page_width,
            page_height=page_height,
            strategy=strategy,
            direction=direction,
        )

    # Default fallback: top-to-bottom, left-to-right
    return sorted(blocks, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id))


def _columns_sort(
    blocks: list[Block],
    page_width: float,
    page_height: float,
    strategy: str,
    direction: str,
) -> list[Block]:
    """Sort blocks using column structure and vertical bands."""
    layout = detect_columns(blocks, page_width, page_height)

    # If single column, sort top to bottom
    if layout.num_columns == 1 and not layout.spans:
        return sorted(blocks, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id))

    # Identify mid-page spans (full width passages or tables) that cut across columns vertically
    mid_spans = [
        s.block
        for s in layout.spans
        if s.span_type in (SpanType.FULL_WIDTH_PASSAGE, SpanType.WIDE_TABLE)
    ]
    mid_spans.sort(key=lambda b: (b.bbox.y1, b.id))

    top_banners = [
        s.block for s in layout.spans if s.span_type == SpanType.TOP_BANNER
    ]
    top_banners.sort(key=lambda b: (b.bbox.y1, b.id))

    bot_banners = [
        s.block for s in layout.spans if s.span_type == SpanType.BOTTOM_BANNER
    ]
    bot_banners.sort(key=lambda b: (b.bbox.y1, b.id))

    # All column blocks
    col_blocks = [b for col in layout.columns for b in col.blocks]

    # If there are mid spans, slice vertical bands
    if mid_spans:
        # Band delimiters
        cuts = [0.0]
        for ms in mid_spans:
            cuts.extend([ms.bbox.y1, ms.bbox.y2])
        cuts.append(page_height)

        result: list[Block] = list(top_banners)
        for i in range(0, len(cuts) - 1, 2):
            y_start, y_end = cuts[i], cuts[i + 1]
            # Find column blocks inside this vertical band
            band_blocks = [
                b for b in col_blocks if y_start <= (b.bbox.y1 + b.bbox.y2) / 2.0 <= y_end
            ]
            if band_blocks:
                result.extend(
                    _order_band_columns(
                        band_blocks,
                        layout.columns,
                        strategy=strategy,
                        direction=direction,
                    )
                )

            # Insert mid span if following
            mid_idx = i // 2
            if mid_idx < len(mid_spans):
                result.append(mid_spans[mid_idx])

        result.extend(bot_banners)
        return result

    # No mid spans: top banners -> columns in order -> bottom banners
    result = list(top_banners)
    cols = layout.columns
    if strategy == "columns_rtl" or direction == "rtl":
        cols = list(reversed(cols))

    for col in cols:
        result.extend(sorted(col.blocks, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id)))

    result.extend(bot_banners)
    return result


def _order_band_columns(
    band_blocks: list[Block],
    columns: list[Any],
    strategy: str,
    direction: str,
) -> list[Block]:
    """Order column blocks within a single horizontal band."""
    cols = columns
    if strategy == "columns_rtl" or direction == "rtl":
        cols = list(reversed(cols))

    ordered: list[Block] = []
    band_block_set = {b.id: b for b in band_blocks}

    for col in cols:
        in_col = [b for b in col.blocks if b.id in band_block_set]
        ordered.extend(sorted(in_col, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id)))

    # Include any band blocks not caught in columns
    caught_ids = {b.id for b in ordered}
    uncaught = [b for b in band_blocks if b.id not in caught_ids]
    if uncaught:
        ordered.extend(sorted(uncaught, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id)))

    return ordered


def _xy_cut_sort(blocks: list[Block], direction: str = "ltr") -> list[Block]:
    """
    Recursive XY-cut algorithm.
    Finds horizontal or vertical whitespace valleys and decomposes recursively.
    """
    if len(blocks) <= 1:
        return list(blocks)

    # 1. Try Horizontal cut (splits vertically into Top and Bottom subsets)
    # Sort blocks by y1
    sorted_y = sorted(blocks, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id))
    h_cut_idx = -1
    max_y2_so_far = sorted_y[0].bbox.y2

    for i in range(1, len(sorted_y)):
        curr_y1 = sorted_y[i].bbox.y1
        if curr_y1 >= max_y2_so_far + 4.0:  # 4pt whitespace gap
            h_cut_idx = i
            break
        if sorted_y[i].bbox.y2 > max_y2_so_far:
            max_y2_so_far = sorted_y[i].bbox.y2

    if h_cut_idx > 0:
        top_group = sorted_y[:h_cut_idx]
        bot_group = sorted_y[h_cut_idx:]
        return _xy_cut_sort(top_group, direction=direction) + _xy_cut_sort(bot_group, direction=direction)

    # 2. Try Vertical cut (splits horizontally into Left and Right subsets)
    sorted_x = sorted(blocks, key=lambda b: (b.bbox.x1, b.bbox.y1, b.id))
    v_cut_idx = -1
    max_x2_so_far = sorted_x[0].bbox.x2

    for i in range(1, len(sorted_x)):
        curr_x1 = sorted_x[i].bbox.x1
        if curr_x1 >= max_x2_so_far + 8.0:  # 8pt vertical column gutter
            v_cut_idx = i
            break
        if sorted_x[i].bbox.x2 > max_x2_so_far:
            max_x2_so_far = sorted_x[i].bbox.x2

    if v_cut_idx > 0:
        left_group = sorted_x[:v_cut_idx]
        right_group = sorted_x[v_cut_idx:]
        if direction == "rtl":
            return _xy_cut_sort(right_group, direction=direction) + _xy_cut_sort(left_group, direction=direction)
        return _xy_cut_sort(left_group, direction=direction) + _xy_cut_sort(right_group, direction=direction)

    # Base case: no clean cuts, sort by (y1, x1)
    if direction == "rtl":
        return sorted(blocks, key=lambda b: (b.bbox.y1, -b.bbox.x1, b.id))
    return sorted(blocks, key=lambda b: (b.bbox.y1, b.bbox.x1, b.id))
