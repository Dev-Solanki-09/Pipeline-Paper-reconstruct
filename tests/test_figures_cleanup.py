"""Tests for black-border removal on scan images."""

from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

from examforge.figures.cleanup import remove_black_borders


class TestBlackBorderCleanup:
    def test_remove_scan_black_border(self):
        """Image with black edges on left and top should have them trimmed."""
        # 200x200 white image with 15px black border on top and left
        im = Image.new("L", (200, 200), color=255)
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, 0, 199, 14], fill=0)  # top border
        draw.rectangle([0, 0, 14, 199], fill=0)  # left border
        # Draw central content
        draw.rectangle([50, 50, 150, 150], fill=128)

        cleaned, crop_offset = remove_black_borders(im, dark_threshold=30, line_density=0.7)

        # The new image should not have the top and left black strip
        assert cleaned.width <= 186
        assert cleaned.height <= 186
        assert crop_offset[0] >= 14  # x-offset
        assert crop_offset[1] >= 14  # y-offset

    def test_clean_image_untouched(self):
        """Image without black borders should be returned unchanged."""
        im = Image.new("L", (100, 100), color=255)
        draw = ImageDraw.Draw(im)
        draw.ellipse([20, 20, 80, 80], outline=0, width=2)

        cleaned, crop_offset = remove_black_borders(im)
        assert cleaned.size == (100, 100)
        assert crop_offset == (0, 0)
