"""Tests for resolution policy and scale classes."""

from __future__ import annotations

import pytest

from examforge.figures.resolution import (
    classify_scale_class,
    compute_target_dpi,
)


class TestResolutionPolicy:
    def test_compute_target_dpi_never_exceeds_native(self):
        """DPI must be clamped to at most native_dpi."""
        # For a small 50 pt box, target_px=1200 would suggest dpi = 1200 / (50/72) = 1728 dpi
        # but native_dpi is 300, so it must clamp to 300.
        dpi = compute_target_dpi(bbox_w=50, bbox_h=50, target_px=1200, min_dpi=150, native_dpi=300)
        assert dpi == 300

    def test_compute_target_dpi_respects_min_dpi(self):
        """DPI must be at least min_dpi."""
        # For a large 700 pt box, target_px=1000 would suggest ~100 dpi, clamped to min_dpi=150
        dpi = compute_target_dpi(bbox_w=500, bbox_h=700, target_px=1000, min_dpi=150, native_dpi=300)
        assert dpi == 150

    def test_scale_class_taxonomy(self):
        """Map dimensions to scale classes properly."""
        assert classify_scale_class(width_px=30, height_px=35) == "img-inline"
        assert classify_scale_class(width_px=180, height_px=60) == "img-opt"
        assert classify_scale_class(width_px=200, height_px=110) == "img-sm"
        assert classify_scale_class(width_px=350, height_px=150) == "img-wide"
        assert classify_scale_class(width_px=400, height_px=300) == "img-lg"
        assert classify_scale_class(width_px=220, height_px=180) == "img-md"
