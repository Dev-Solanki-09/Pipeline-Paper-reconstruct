"""Tests for clean/watermark_median.py: cross-page median watermark estimation and subtraction."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from examforge.clean.watermark_median import (
    calculate_residual_correlation,
    estimate_watermark_median,
    remove_baked_watermark,
)
from examforge.ir.schema import Issue


def _generate_synthetic_watermarked_pages(
    count: int = 6,
    width: int = 300,
    height: int = 400,
    add_watermark: bool = True,
) -> list[Image.Image]:
    """Generate pages with varied text content and a constant diagonal watermark."""
    pages: list[Image.Image] = []

    # Prepare constant watermark layer (e.g. diagonal watermark band)
    wm_mask = np.ones((height, width), dtype=np.float32)
    if add_watermark:
        for y in range(height):
            for x in range(width):
                if 120 <= (y + x) <= 180:
                    wm_mask[y, x] = 0.75  # 25% darkening watermark

    for i in range(count):
        im = Image.new("L", (width, height), color=255)
        draw = ImageDraw.Draw(im)
        # Unique text lines on each page
        for line_idx in range(5):
            y = 50 + line_idx * 60 + (i * 7) % 20
            draw.line([(40, y), (260, y)], fill=0, width=3)
            draw.text((45, y - 12), f"Page {i} Q{line_idx+1}", fill=0)

        arr = np.array(im, dtype=np.float32)
        blended = np.clip(arr * wm_mask, 0, 255).astype(np.uint8)
        pages.append(Image.fromarray(blended))

    return pages


class TestCleanWatermarkMedian:
    def test_estimate_and_remove_fixed_watermark(self):
        """Cross-page median estimates the watermark and flat-field removes it (R03 < 0.05)."""
        pages = _generate_synthetic_watermarked_pages(count=6, add_watermark=True)

        wm_layer = estimate_watermark_median(pages)
        assert wm_layer is not None

        # Clean each page
        cleaned_pages, issues = remove_baked_watermark(pages, wm_layer=wm_layer)
        assert len(cleaned_pages) == 6
        assert len(issues) == 0

        # Check residual correlation (R03) on cleaned page
        # Residual correlation should be < 0.05
        corr = calculate_residual_correlation(cleaned_pages[0], wm_layer)
        assert corr < 0.05

    def test_negative_control_no_watermark(self):
        """When pages have no watermark, output is unchanged."""
        pages = _generate_synthetic_watermarked_pages(count=4, add_watermark=False)
        wm_layer = estimate_watermark_median(pages)

        # Without watermark, median is near-uniform white (>250 everywhere)
        assert wm_layer is not None
        assert np.mean(wm_layer) >= 250

        cleaned_pages, _ = remove_baked_watermark(pages, wm_layer=wm_layer)
        # Pixel values should match closely
        diff = np.abs(np.array(cleaned_pages[0], dtype=float) - np.array(pages[0], dtype=float))
        assert np.mean(diff) < 2.0

    def test_moving_watermark_records_issue(self):
        """When watermark changes position across pages, records an Issue and warns."""
        # Page 1 has watermark at top, Page 2 at bottom
        pages = []
        for i in range(4):
            im = Image.new("L", (200, 200), color=255)
            draw = ImageDraw.Draw(im)
            y = 30 + i * 40
            draw.rectangle([20, y, 180, y + 25], fill=180)  # moving box
            pages.append(im)

        _, issues = remove_baked_watermark(pages, check_alignment=True)
        assert len(issues) >= 1
        assert "watermark" in issues[0].message.lower()
