"""Tests for clean/branding.py: branding scrubber and false-positive guards."""

from __future__ import annotations

import pytest

from examforge.clean.branding import (
    is_false_positive_trap,
    scrub_branding_blocks,
)
from examforge.ir.schema import BBox, Block, BlockStatus, BlockType, Lang


def _block(bid: str, text: str, norm_y: float = 0.05) -> Block:
    return Block(
        id=bid,
        page=1,
        type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=int(norm_y * 800), x2=550, y2=int((norm_y + 0.03) * 800)),
        bbox_norm=(0.1, norm_y, 0.9, norm_y + 0.03),
        order=0,
        lang=Lang.EN,
        text=text,
        confidence=1.0,
        status=BlockStatus.TRUSTED,
    )


class TestCleanBranding:
    def test_scrub_url_and_phone(self):
        """URLs and standalone 10-digit phone numbers are identified."""
        b_url = _block("b1", "Download solutions at https://example-coaching.com/tests")
        b_phone = _block("b2", "Helpline: 9876543210 (10 AM to 6 PM)")
        b_clean = _block("b3", "A particle of mass m moves in a circle", norm_y=0.40)

        dropped = scrub_branding_blocks([b_url, b_phone, b_clean])
        assert "b1" in dropped
        assert "b2" in dropped
        assert "b3" not in dropped

    def test_false_positive_constants_traps(self):
        """Physical constants and scientific units must NEVER be identified as branding."""
        constants = [
            "Take g = 9.8 m/s^2 and c = 3 x 10^8 m/s",
            "Universal gas constant R = 8.314 J/(mol K)",
            "Planck's constant h = 6.626 x 10^-34 J s",
            "Permittivity of free space eps_0 = 8.85 x 10^-12 F/m",
        ]
        for c in constants:
            assert is_false_positive_trap(c) is True
            b = _block("b_const", c)
            assert "b_const" not in scrub_branding_blocks([b])

    def test_false_positive_abbreviations_and_chemistry(self):
        """Abbreviations (e.g., i.e.) and chemical formulas must NEVER be dropped."""
        safe_texts = [
            "e.g., in the case of adiabatic expansion",
            "i.e., when temperature remains constant",
            "A solution of NaCl and AgNO3 is mixed",
            "Reaction with concentrated H2SO4 at 100 C",
        ]
        for text in safe_texts:
            assert is_false_positive_trap(text) is True
            b = _block("b_chem", text)
            assert "b_chem" not in scrub_branding_blocks([b])
