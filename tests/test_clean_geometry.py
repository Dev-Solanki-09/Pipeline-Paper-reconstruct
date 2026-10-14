"""Tests for clean/geometry.py: orientation, deskew, and two-up spread splitting."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from examforge.clean.geometry import (
    correct_orientation,
    deskew_image,
    detect_orientation,
    detect_skew_angle,
    split_two_up_spread,
)


def _draw_horizontal_text_lines(
    width: int = 400,
    height: int = 500,
    line_count: int = 8,
) -> Image.Image:
    """Draw clean horizontal text-like lines on an image."""
    im = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(im)
    for i in range(line_count):
        y = 50 + i * 45
        draw.line([(50, y), (350, y)], fill=0, width=4)
        draw.line([(50, y + 8), (280, y + 8)], fill=0, width=3)
    return im


class TestCleanGeometry:
    def test_orientation_detection_and_correction(self):
        """Image rotated by 90, 180, or 270 degrees is detected and righted."""
        base = _draw_horizontal_text_lines()

        for expected_angle in [0, 90, 180, 270]:
            rotated = base.rotate(expected_angle, expand=True, fillcolor=255)
            detected = detect_orientation(rotated)
            # Either matches angle directly or corrects to 0
            corrected = correct_orientation(rotated, angle=detected)
            # Corrected image should be back in standard portrait orientation
            assert corrected.height >= corrected.width

    def test_deskew_angle_detection_and_correction(self):
        """Skewed image within +/- 15 degrees is detected and deskewed."""
        base = _draw_horizontal_text_lines()

        for true_skew in [-8.0, 6.5, 12.0]:
            # Rotate by small skew
            skewed = base.rotate(true_skew, expand=True, fillcolor=255)
            detected_skew = detect_skew_angle(skewed, max_angle=15.0)

            # Detected angle should match the true rotation within 1.5 degrees
            assert abs(detected_skew - true_skew) <= 1.5

            deskewed = deskew_image(skewed, detected_skew)
            # After deskewing, remaining skew should be close to 0
            rem_angle = detect_skew_angle(deskewed, max_angle=5.0)
            assert abs(rem_angle) <= 1.0

    def test_split_two_up_spread(self):
        """A two-up landscape spread (width > 1.4 * height) splits cleanly into two portrait pages."""
        spread = Image.new("L", (1000, 600), color=255)
        draw = ImageDraw.Draw(spread)

        # Left page content
        draw.rectangle([100, 100, 400, 500], outline=0, width=2)
        # Right page content
        draw.rectangle([600, 100, 900, 500], outline=0, width=2)
        # Central gutter line
        draw.line([(500, 50), (500, 550)], fill=128, width=1)

        left_page, right_page = split_two_up_spread(spread, gutter_x=500)

        assert left_page.width == 500
        assert left_page.height == 600
        assert right_page.width == 500
        assert right_page.height == 600
        assert left_page.height > left_page.width  # portrait
