"""Tests for multi-column detection and span classification (Phase 6.1)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import BBox, Block
from examforge.layout.columns import (
    ColumnLayout,
    SpanType,
    detect_columns,
)


def _make_block(id: str, x1: float, y1: float, x2: float, y2: float, text: str = "sample text") -> Block:
    return Block(
        id=id,
        page=1,
        bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
        text=text,
    )


class TestColumnDetection:
    def test_single_column_page(self):
        page_w, page_h = 600.0, 800.0
        blocks = [
            _make_block("b1", 50, 50, 550, 100),
            _make_block("b2", 50, 120, 550, 200),
            _make_block("b3", 50, 220, 550, 350),
            _make_block("b4", 50, 370, 550, 500),
        ]
        layout = detect_columns(blocks, page_w, page_h)
        assert layout.num_columns == 1
        assert len(layout.columns) == 1
        assert len(layout.spans) == 0

    def test_two_column_page_with_gutter(self):
        page_w, page_h = 600.0, 800.0
        # Left col: x in [40, 280], Right col: x in [320, 560], Gutter in [280, 320]
        blocks = [
            _make_block("l1", 40, 100, 280, 200),
            _make_block("l2", 40, 220, 280, 350),
            _make_block("l3", 40, 370, 280, 500),
            _make_block("r1", 320, 100, 560, 200),
            _make_block("r2", 320, 220, 560, 350),
            _make_block("r3", 320, 370, 560, 500),
        ]
        layout = detect_columns(blocks, page_w, page_h)
        assert layout.num_columns == 2
        assert len(layout.columns) == 2
        # Verify left and right assignments
        col0_ids = {b.id for b in layout.columns[0].blocks}
        col1_ids = {b.id for b in layout.columns[1].blocks}
        assert col0_ids == {"l1", "l2", "l3"}
        assert col1_ids == {"r1", "r2", "r3"}

    def test_three_column_page(self):
        page_w, page_h = 900.0, 600.0
        # Col 0: 50..250, Col 1: 350..550, Col 2: 650..850
        blocks = [
            _make_block("c1_1", 50, 100, 250, 300),
            _make_block("c1_2", 50, 320, 250, 500),
            _make_block("c2_1", 350, 100, 550, 300),
            _make_block("c2_2", 350, 320, 550, 500),
            _make_block("c3_1", 650, 100, 850, 300),
            _make_block("c3_2", 650, 320, 850, 500),
        ]
        layout = detect_columns(blocks, page_w, page_h)
        assert layout.num_columns == 3
        assert len(layout.columns) == 3

    def test_two_column_with_top_banner_and_bottom_banner(self):
        page_w, page_h = 600.0, 800.0
        # Top banner spans 40..560 at y: 20..80
        # Bottom banner spans 40..560 at y: 720..770
        banner_top = _make_block("top_banner", 40, 20, 560, 80, text="EXAMINATION INSTRUCTIONS")
        banner_bot = _make_block("bot_banner", 40, 720, 560, 770, text="END OF SECTION")
        col_blocks = [
            _make_block("l1", 40, 120, 280, 250),
            _make_block("l2", 40, 280, 280, 450),
            _make_block("r1", 320, 120, 560, 250),
            _make_block("r2", 320, 280, 560, 450),
        ]
        all_blocks = [banner_top, banner_bot] + col_blocks
        layout = detect_columns(all_blocks, page_w, page_h)

        assert layout.num_columns == 2
        assert len(layout.spans) == 2
        span_types = {s.block.id: s.span_type for s in layout.spans}
        assert span_types["top_banner"] == SpanType.TOP_BANNER
        assert span_types["bot_banner"] == SpanType.BOTTOM_BANNER

    def test_spanning_table_in_middle(self):
        page_w, page_h = 600.0, 800.0
        table_span = _make_block("table_mid", 40, 350, 560, 480, text="Table: Properties of Elements")
        blocks = [
            _make_block("l1", 40, 100, 280, 300),
            _make_block("r1", 320, 100, 560, 300),
            table_span,
            _make_block("l2", 40, 520, 280, 700),
            _make_block("r2", 320, 520, 560, 700),
        ]
        layout = detect_columns(blocks, page_w, page_h)
        assert layout.num_columns == 2
        assert any(
            s.block.id == "table_mid" and s.span_type in (SpanType.FULL_WIDTH_PASSAGE, SpanType.WIDE_TABLE)
            for s in layout.spans
        )

    def test_jagged_gutters_tolerance(self):
        page_w, page_h = 600.0, 800.0
        # Columns have jittery boundaries (+/- 15px)
        blocks = [
            _make_block("l1", 45, 100, 275, 200),
            _make_block("l2", 40, 220, 290, 350),
            _make_block("l3", 50, 370, 285, 500),
            _make_block("r1", 315, 100, 555, 200),
            _make_block("r2", 330, 220, 560, 350),
            _make_block("r3", 325, 370, 550, 500),
        ]
        layout = detect_columns(blocks, page_w, page_h)
        assert layout.num_columns == 2
