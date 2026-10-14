"""Tests for clean/furniture.py: script-aware page numbers and repeating furniture detection."""

from __future__ import annotations

import pytest

from examforge.clean.furniture import (
    detect_page_numbers_script_aware,
    find_repeating_furniture_blocks,
)
from examforge.ir.schema import BBox, Block, BlockStatus, BlockType, Lang


def _block(
    bid: str,
    page: int,
    text: str,
    norm_y1: float,
    norm_y2: float,
    lang: Lang = Lang.EN,
) -> Block:
    return Block(
        id=bid,
        page=page,
        type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=int(norm_y1 * 800), x2=550, y2=int(norm_y2 * 800)),
        bbox_norm=(0.1, norm_y1, 0.9, norm_y2),
        order=0,
        lang=lang,
        text=text,
        confidence=1.0,
        status=BlockStatus.TRUSTED,
    )


class TestCleanFurniture:
    def test_repeating_header_footer_across_pages(self):
        """Header appearing at norm_y1 < 0.10 across 4 pages is identified as furniture."""
        blocks = []
        for p in range(1, 5):
            blocks.append(_block(f"h_{p}", page=p, text="PHYSICS - SECTION A", norm_y1=0.04, norm_y2=0.07))
            blocks.append(_block(f"f_{p}", page=p, text="SPACE FOR ROUGH WORK", norm_y1=0.92, norm_y2=0.96))
            blocks.append(_block(f"q_{p}", page=p, text=f"{p}. Calculate the kinetic energy...", norm_y1=0.20, norm_y2=0.30))

        furniture_ids = find_repeating_furniture_blocks(blocks, min_fraction=0.6)
        assert "h_1" in furniture_ids and "h_4" in furniture_ids
        assert "f_1" in furniture_ids and "f_4" in furniture_ids
        # Real question content must never be dropped
        assert "q_1" not in furniture_ids and "q_4" not in furniture_ids

    def test_devanagari_page_number_detection(self):
        """Devanagari numerals (१, २, ३) in footer are recognized as page numbers."""
        b1 = _block("dp_1", page=1, text="पृष्ठ १", norm_y1=0.94, norm_y2=0.97, lang=Lang.HI)
        b2 = _block("dp_2", page=2, text="पृष्ठ २", norm_y1=0.94, norm_y2=0.97, lang=Lang.HI)
        b3 = _block("dp_3", page=3, text="पृष्ठ ३", norm_y1=0.94, norm_y2=0.97, lang=Lang.HI)
        b_q = _block("q_1", page=1, text="१. एक कण विरामावस्था से चलना प्रारम्भ करता है...", norm_y1=0.20, norm_y2=0.30, lang=Lang.HI)

        pn_ids = detect_page_numbers_script_aware([b1, b2, b3, b_q])
        assert "dp_1" in pn_ids
        assert "dp_2" in pn_ids
        assert "dp_3" in pn_ids
        assert "q_1" not in pn_ids

    def test_roman_page_number_detection(self):
        """Roman numerals (i, ii, iii) in footer are recognized as page numbers."""
        b1 = _block("rp_1", page=1, text="i", norm_y1=0.95, norm_y2=0.98)
        b2 = _block("rp_2", page=2, text="ii", norm_y1=0.95, norm_y2=0.98)
        b3 = _block("rp_3", page=3, text="iii", norm_y1=0.95, norm_y2=0.98)

        pn_ids = detect_page_numbers_script_aware([b1, b2, b3])
        assert "rp_1" in pn_ids and "rp_2" in pn_ids and "rp_3" in pn_ids

    def test_question_guard_preserves_content(self):
        """Long blocks or question numberings are never identified as furniture."""
        # Block starting with question number
        b_num = _block("b_num", page=1, text="12. In a Young's double slit experiment...", norm_y1=0.05, norm_y2=0.08)
        # Block with option label
        b_opt = _block("b_opt", page=1, text="(A) 2.5 m/s", norm_y1=0.06, norm_y2=0.09)
        # Long passage block
        b_long = _block("b_long", page=1, text="Read the following passage carefully and answer the questions: An ideal gas undergoes cyclic process...", norm_y1=0.07, norm_y2=0.15)

        furniture_ids = find_repeating_furniture_blocks([b_num, b_opt, b_long] * 3, min_fraction=0.5)
        assert len(furniture_ids) == 0
