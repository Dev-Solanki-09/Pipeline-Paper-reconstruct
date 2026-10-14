"""Tests for reading order algorithms and metamorphic properties (Phase 6.2)."""

from __future__ import annotations

import random
import pytest

from examforge.ir.schema import BBox, Block
from examforge.layout.reading_order import order_blocks


def _make_block(id: str, x1: float, y1: float, x2: float, y2: float, text: str = "") -> Block:
    return Block(id=id, page=1, bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2), text=text or f"Block {id}")


class TestReadingOrder:
    def test_single_column_top_to_bottom(self):
        page_w, page_h = 600.0, 800.0
        blocks = [
            _make_block("b3", 50, 300, 550, 400),
            _make_block("b1", 50, 50, 550, 150),
            _make_block("b2", 50, 180, 550, 280),
        ]
        ordered = order_blocks(blocks, page_w, page_h, strategy="columns_ltr")
        assert [b.id for b in ordered] == ["b1", "b2", "b3"]

    def test_two_column_ltr(self):
        page_w, page_h = 600.0, 800.0
        # Banner at top, left col (l1, l2), right col (r1, r2)
        top = _make_block("top", 40, 20, 560, 60)
        l1 = _make_block("l1", 40, 100, 280, 200)
        l2 = _make_block("l2", 40, 250, 280, 350)
        r1 = _make_block("r1", 320, 100, 560, 200)
        r2 = _make_block("r2", 320, 250, 560, 350)

        blocks = [r2, l1, top, r1, l2]
        ordered = order_blocks(blocks, page_w, page_h, strategy="columns_ltr")
        assert [b.id for b in ordered] == ["top", "l1", "l2", "r1", "r2"]

    def test_two_column_rtl(self):
        page_w, page_h = 600.0, 800.0
        top = _make_block("top", 40, 20, 560, 60)
        l1 = _make_block("l1", 40, 100, 280, 200)
        l2 = _make_block("l2", 40, 250, 280, 350)
        r1 = _make_block("r1", 320, 100, 560, 200)
        r2 = _make_block("r2", 320, 250, 560, 350)

        blocks = [l2, r1, top, l1, r2]
        ordered = order_blocks(blocks, page_w, page_h, strategy="columns_rtl")
        # In RTL, top first, then right column top-to-bottom, then left column top-to-bottom
        assert [b.id for b in ordered] == ["top", "r1", "r2", "l1", "l2"]

    def test_xy_cut_complex_nesting(self):
        page_w, page_h = 600.0, 800.0
        header = _make_block("h", 40, 20, 560, 60)
        # Left side
        l1 = _make_block("l1", 40, 100, 280, 200)
        l2 = _make_block("l2", 40, 220, 280, 350)
        # Mid separator span
        mid = _make_block("mid", 40, 380, 560, 420)
        # Lower section single column
        bot1 = _make_block("bot1", 40, 450, 560, 550)
        bot2 = _make_block("bot2", 40, 570, 560, 670)

        blocks = [bot2, l2, header, mid, bot1, l1]
        ordered = order_blocks(blocks, page_w, page_h, strategy="xy_cut")
        # header -> l1, l2 -> mid -> bot1 -> bot2
        assert [b.id for b in ordered] == ["h", "l1", "l2", "mid", "bot1", "bot2"]

    def test_metamorphic_shuffling_invariance(self):
        """Property: Shuffling the input blocks order must ALWAYS produce the exact same reading order."""
        page_w, page_h = 600.0, 800.0
        blocks = [
            _make_block(f"b{i}", x1, y1, x2, y2)
            for i, (x1, y1, x2, y2) in enumerate([
                (40, 20, 560, 80),   # top banner
                (40, 100, 280, 200),  # left 1
                (40, 220, 280, 340),  # left 2
                (40, 360, 280, 480),  # left 3
                (320, 100, 560, 200), # right 1
                (320, 220, 560, 340), # right 2
                (320, 360, 560, 480), # right 3
                (40, 500, 560, 560),  # mid banner
                (40, 580, 560, 700),  # bot full
            ])
        ]

        expected_order = [b.id for b in order_blocks(blocks, page_w, page_h, strategy="columns_ltr")]

        rng = random.Random(42)
        for trial in range(20):
            shuffled = list(blocks)
            rng.shuffle(shuffled)
            result = order_blocks(shuffled, page_w, page_h, strategy="columns_ltr")
            assert [b.id for b in result] == expected_order, f"Mismatch on trial {trial}"

    def test_metamorphic_scaling_invariance(self):
        """Property: Rescaling page and bboxes by factor k leaves reading order unchanged."""
        page_w, page_h = 600.0, 800.0
        blocks = [
            _make_block("top", 40, 20, 560, 80),
            _make_block("l1", 40, 100, 280, 200),
            _make_block("l2", 40, 220, 280, 340),
            _make_block("r1", 320, 100, 560, 200),
            _make_block("r2", 320, 220, 560, 340),
        ]
        base_order = [b.id for b in order_blocks(blocks, page_w, page_h, strategy="columns_ltr")]

        for scale in [0.5, 1.5, 2.0]:
            scaled_blocks = [
                Block(
                    id=b.id,
                    page=1,
                    bbox=BBox(
                        x1=b.bbox.x1 * scale,
                        y1=b.bbox.y1 * scale,
                        x2=b.bbox.x2 * scale,
                        y2=b.bbox.y2 * scale,
                    ),
                    text=b.text,
                )
                for b in blocks
            ]
            scaled_order = [
                b.id for b in order_blocks(scaled_blocks, page_w * scale, page_h * scale, strategy="columns_ltr")
            ]
            assert scaled_order == base_order, f"Scale {scale} altered order"
