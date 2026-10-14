"""Tests for refine_bbox (grow-until-clean, shrink-to-ink, text-mask subtraction)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from examforge.figures.crop import (
    calculate_border_strip_ink_ratio,
    refine_bbox,
    shrink_to_ink,
)
from examforge.ir.schema import BBox


def _create_synthetic_diagram_page(
    page_w: int = 600,
    page_h: int = 800,
    diagram_box: tuple[int, int, int, int] = (150, 200, 350, 380),
    label_box: tuple[int, int, int, int] = (320, 210, 345, 230),  # In-figure label "R1"
    stem_text_box: tuple[int, int, int, int] = (100, 100, 500, 170),  # Question stem text
    option_box: tuple[int, int, int, int] = (100, 420, 300, 460),  # Option text
) -> Image.Image:
    """Create a page with a diagram, an in-figure label, and neighboring question text."""
    im = Image.new("L", (page_w, page_h), color=255)
    draw = ImageDraw.Draw(im)

    # Draw diagram (e.g. circle with cross)
    d_x1, d_y1, d_x2, d_y2 = diagram_box
    draw.ellipse([d_x1, d_y1, d_x2, d_y2], outline=0, width=3)
    draw.line([(d_x1, (d_y1 + d_y2) // 2), (d_x2, (d_y1 + d_y2) // 2)], fill=0, width=2)

    # In-figure label "R1" inside or immediately adjacent to diagram
    l_x1, l_y1, l_x2, l_y2 = label_box
    draw.rectangle([l_x1, l_y1, l_x2, l_y2], fill=0)

    # Stem text lines
    s_x1, s_y1, s_x2, s_y2 = stem_text_box
    for y in range(s_y1 + 10, s_y2, 15):
        draw.line([(s_x1, y), (s_x2, y)], fill=50, width=3)

    # Option text lines
    o_x1, o_y1, o_x2, o_y2 = option_box
    for y in range(o_y1 + 10, o_y2, 15):
        draw.line([(o_x1, y), (o_x2, y)], fill=50, width=3)

    return im


class TestRefineBBox:
    def test_grow_until_clean_zero_border_strip_ink(self):
        """Border-strip ink ratio == 0 for 100% of refined crops."""
        page_img = _create_synthetic_diagram_page()
        # Seed bbox that cuts through the diagram slightly or is rough
        seed = BBox(x1=160, y1=210, x2=340, y2=370)

        refined = refine_bbox(
            image=page_img,
            seed_bbox=seed,
            page_width=600,
            page_height=800,
            max_expand=35,
        )

        # Border strip (2-px) ink ratio must be strictly 0.0
        strip_ratio = calculate_border_strip_ink_ratio(
            page_img, refined, strip_width=2, ink_threshold=200
        )
        assert strip_ratio == 0.0

    def test_idempotent_property(self):
        """Property: refine_bbox(refine_bbox(b)) == refine_bbox(b)."""
        page_img = _create_synthetic_diagram_page()
        seed = BBox(x1=145, y1=195, x2=355, y2=385)

        first_pass = refine_bbox(
            image=page_img,
            seed_bbox=seed,
            page_width=600,
            page_height=800,
        )
        second_pass = refine_bbox(
            image=page_img,
            seed_bbox=first_pass,
            page_width=600,
            page_height=800,
        )

        assert first_pass == second_pass

    def test_monotone_property(self):
        """Property: refined bbox is never smaller than the initial seed's inner ink bbox."""
        page_img = _create_synthetic_diagram_page()
        seed = BBox(x1=150, y1=200, x2=350, y2=380)

        inner_ink = shrink_to_ink(page_img, seed)
        refined = refine_bbox(page_img, seed, page_width=600, page_height=800)

        # Refined bbox must contain inner_ink
        assert refined.x1 <= inner_ink.x1
        assert refined.y1 <= inner_ink.y1
        assert refined.x2 >= inner_ink.x2
        assert refined.y2 >= inner_ink.y2

    def test_page_bounds_preserved(self):
        """Property: refined bbox never exceeds page dimensions."""
        im = Image.new("L", (100, 100), color=255)
        # ink near the top-left corner
        draw = ImageDraw.Draw(im)
        draw.rectangle([1, 1, 30, 30], fill=0)

        seed = BBox(x1=2, y1=2, x2=28, y2=28)
        refined = refine_bbox(im, seed, page_width=100, page_height=100, max_expand=20)

        assert refined.x1 >= 0
        assert refined.y1 >= 0
        assert refined.x2 <= 100
        assert refined.y2 <= 100

    def test_text_mask_subtraction_while_attaching_in_figure_labels(self):
        """Stem/option text mask is excluded, while in-figure label is retained."""
        page_img = _create_synthetic_diagram_page()
        # Stem is at 100..170. Option is at 420..460.
        stem_box = BBox(x1=100, y1=100, x2=500, y2=170)
        option_box = BBox(x1=100, y1=420, x2=300, y2=460)
        label_box = BBox(x1=320, y1=210, x2=345, y2=230)

        # Seed covers diagram (150..350, 200..380)
        seed = BBox(x1=140, y1=190, x2=360, y2=390)

        refined = refine_bbox(
            image=page_img,
            seed_bbox=seed,
            text_mask=[stem_box, option_box],
            in_figure_labels=[label_box],
            page_width=600,
            page_height=800,
        )

        # Does not extend into stem or option
        assert refined.y1 >= 170
        assert refined.y2 <= 420
        # In-figure label is fully enclosed
        assert refined.x1 <= label_box.x1 and refined.y1 <= label_box.y1
        assert refined.x2 >= label_box.x2 and refined.y2 >= label_box.y2
