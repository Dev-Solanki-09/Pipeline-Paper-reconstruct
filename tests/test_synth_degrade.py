"""Tests for synthetic page degradation engine."""

from __future__ import annotations

import numpy as np
from PIL import Image

from examforge.synth.degrade import degrade_page


def test_degrade_levels_dimensions():
    """All degradation levels must preserve or provide valid RGB image."""
    base_im = Image.new("RGB", (300, 400), color=(255, 255, 255))

    for lvl in ["L0", "L1", "L2", "L3", "L4"]:
        deg = degrade_page(base_im, level=lvl, seed=42)  # type: ignore
        assert isinstance(deg, Image.Image)
        assert deg.size == (300, 400)


def test_degrade_determinism():
    """Same level and seed must produce identical pixels."""
    base_im = Image.new("RGB", (200, 250), color=(240, 240, 240))

    deg1 = degrade_page(base_im, level="L2", seed=99)
    deg2 = degrade_page(base_im, level="L2", seed=99)

    arr1 = np.array(deg1)
    arr2 = np.array(deg2)
    assert np.array_equal(arr1, arr2)


def test_l0_unaltered():
    """L0 should not alter image."""
    base_im = Image.new("RGB", (100, 100), color=(128, 128, 128))
    deg = degrade_page(base_im, level="L0", seed=1)
    assert np.array_equal(np.array(base_im), np.array(deg))
