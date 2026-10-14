"""Tests for legacy-font detection and KrutiDev/Chanakya transliteration."""

from __future__ import annotations

import pytest

from examforge.lang.fontmaps import (
    convert_legacy_font,
    detect_legacy_font,
    needs_ocr_for_script,
)


class TestFontDetection:
    def test_detect_by_font_name(self):
        font_id, conf = detect_legacy_font("Some text", font_name="KrutiDev010")
        assert font_id == "krutidev010"
        assert conf >= 0.9

        font_id2, conf2 = detect_legacy_font("Some text", font_name="Chanakya-Bold")
        assert font_id2 == "chanakya"
        assert conf2 >= 0.9

    def test_detect_by_frequency_heuristic(self):
        # "[k?kFk/kHk" has frequent KrutiDev digraphs representing ख, घ, थ, ध, भ
        kruti_sample = "d [k x ?k p t"
        font_id, conf = detect_legacy_font(kruti_sample, font_name=None)
        assert font_id == "krutidev010"
        assert conf >= 0.6

    def test_clean_english_not_detected_as_legacy_font(self):
        english_sample = "Calculate the total velocity and acceleration of the moving body."
        font_id, conf = detect_legacy_font(english_sample, font_name="Arial")
        assert font_id is None
        assert conf < 0.3


class TestKrutiDevConversion:
    def test_simple_consonants_and_vowels(self):
        # 'd' -> क, 'x' -> ग
        assert convert_legacy_font("d x", font_name="KrutiDev010") == "क ग"

    def test_digraph_consonants(self):
        # '[k' -> ख, '?k' -> घ, 'Fk' -> थ
        assert convert_legacy_font("[k ?k Fk", font_name="KrutiDev010") == "ख घ थ"

    def test_matras_and_danda(self):
        # 'd' + 'k' -> 'का'
        # 'A' -> '।'
        assert convert_legacy_font("dk A", font_name="KrutiDev010") == "का ।"

    def test_prefix_i_matra(self):
        # In KrutiDev, 'fd' -> 'कि' ('f' is prepended to 'd')
        assert convert_legacy_font("fd", font_name="KrutiDev010") == "कि"
        # 'f[k' -> 'खि'
        assert convert_legacy_font("f[k", font_name="KrutiDev010") == "खि"

    def test_reph(self):
        # 'dZ' -> 'र्क'
        assert convert_legacy_font("dZ", font_name="KrutiDev010") == "र्क"

    def test_full_word_roundtrip(self):
        # 'Hkkjr' -> 'भारत'
        assert convert_legacy_font("Hkkjr", font_name="KrutiDev010") == "भारत"

    def test_needs_ocr_fallback_for_garbled_bytes(self):
        # Text with unknown control characters / unmapped private-use codes
        garbled = "\x81\x82\x83\x84"
        assert needs_ocr_for_script(garbled, font_name="KrutiDev010") is True
        assert needs_ocr_for_script("Hkkjr", font_name="KrutiDev010") is False
