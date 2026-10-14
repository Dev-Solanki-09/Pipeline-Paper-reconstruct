"""Tests for clean/illumination.py: background estimation and flat-field division."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from examforge.clean.illumination import (
    calculate_ssim,
    flatten_illumination,
)


def _create_shadowed_page(
    width: int = 300,
    height: int = 400,
) -> tuple[Image.Image, Image.Image]:
    """Create a clean page and a shadowed version with a severe lighting gradient."""
    # Clean page
    clean_im = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(clean_im)
    for y in range(40, 360, 35):
        draw.line([(30, y), (270, y)], fill=0, width=3)
        draw.text((35, y - 15), f"Line text at y={y}", fill=0)

    clean_arr = np.array(clean_im, dtype=np.float32)

    # Gradient shadow from top (100% brightness) to bottom (50% brightness)
    gradient = np.linspace(1.0, 0.45, height, dtype=np.float32)[:, None]
    shadowed_arr = np.clip(clean_arr * gradient, 0, 255).astype(np.uint8)
    shadowed_im = Image.fromarray(shadowed_arr)

    return clean_im, shadowed_im


class TestCleanIllumination:
    def test_flatten_illumination_removes_shadow(self):
        """Shadowed image has background normalized and dark text preserved."""
        clean_im, shadowed_im = _create_shadowed_page()

        flattened = flatten_illumination(shadowed_im, kernel_size=25)

        # Background corners of flattened should be close to 255
        flat_arr = np.array(flattened)
        # Top-right corner (no text)
        assert flat_arr[10, 280] >= 240
        # Bottom-right corner (previously dark shadowed)
        assert flat_arr[380, 280] >= 235

    def test_content_preservation_high_ssim(self):
        """Cleaned text over content mask retains high structural similarity (SSIM >= 0.95)."""
        clean_im, shadowed_im = _create_shadowed_page()
        flattened = flatten_illumination(shadowed_im, kernel_size=25)

        # Calculate SSIM over the content mask
        clean_arr = np.array(clean_im)
        flat_arr = np.array(flattened)
        mask = clean_arr < 220  # content mask

        ssim_score = calculate_ssim(clean_arr, flat_arr, mask=mask)
        assert ssim_score >= 0.95
