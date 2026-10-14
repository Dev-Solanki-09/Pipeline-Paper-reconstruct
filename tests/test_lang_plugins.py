"""Tests for English, Hindi, and scaffolded language plugins."""

from __future__ import annotations

import unicodedata
import pytest

from examforge.lang.registry import get_plugin


class TestEnglishPlugin:
    def test_english_normalization(self):
        plugin = get_plugin("en")
        raw = '“Hello World” – ‘Test’ — 100%'
        norm = plugin.normalize(raw)
        # Check standard quotes / dashes handled cleanly
        assert "Hello World" in norm

    def test_english_digits(self):
        plugin = get_plugin("en")
        assert plugin.digits_map.get("0") == "0"
        assert plugin.normalize("12345") == "12345"


class TestHindiPlugin:
    def test_nfc_idempotence(self):
        plugin = get_plugin("hi")
        # Decomposed Devanagari characters: ka + nukta
        decomposed = "क\u093Cल"
        norm1 = plugin.normalize(decomposed)
        norm2 = plugin.normalize(norm1)
        assert norm1 == norm2
        assert norm1 == "क़ल"

    def test_contextual_danda(self):
        plugin = get_plugin("hi")
        # Preceded by Devanagari -> converted to danda
        text1 = "यह एक परीक्षण है |"
        assert plugin.normalize(text1) == "यह एक परीक्षण है ।"

        # Double pipe -> double danda
        text2 = "अध्याय समाप्त ||"
        assert plugin.normalize(text2) == "अध्याय समाप्त ॥"

        # Math pipe should NOT be converted to danda
        math_text = "|x| = 5"
        assert plugin.normalize(math_text) == "|x| = 5"

    def test_zwnj_zwj_cleanup(self):
        plugin = get_plugin("hi")
        # Spurious ZWNJ at boundary
        text_with_boundary_zwnj = "नमस्ते \u200C दुनिया"
        cleaned = plugin.normalize(text_with_boundary_zwnj)
        assert "\u200C" not in cleaned

    def test_hindi_digits_map(self):
        plugin = get_plugin("hi")
        devanagari_num = "१२३४५६७८९०"
        converted = "".join(plugin.digits_map.get(ch, ch) for ch in devanagari_num)
        assert converted == "1234567890"


class TestScaffoldedPlugins:
    @pytest.mark.parametrize(
        "lang_code, native_digit_sample, expected_ascii",
        [
            ("bn", "১২৩৪৫", "12345"),
            ("ta", "௧௨௩௪௫", "12345"),
            ("te", "౧౨౩౪౫", "12345"),
            ("kn", "೧೨೩೪೫", "12345"),
            ("ml", "൧൨൩൪൫", "12345"),
            ("gu", "૧૨૩૪૫", "12345"),
            ("pa", "੧੨੩੪੫", "12345"),
            ("or", "୧୨୩୪୫", "12345"),
            ("mr", "१२३४५", "12345"),
            ("ur", "۱۲۳۴۵", "12345"),
            ("ar", "١٢٣٤٥", "12345"),
            ("zh", "１２３４５", "12345"),
        ],
    )
    def test_digit_mapping(self, lang_code, native_digit_sample, expected_ascii):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plugin = get_plugin(lang_code)
            converted = "".join(plugin.digits_map.get(ch, ch) for ch in native_digit_sample)
            assert converted == expected_ascii

    @pytest.mark.parametrize("lang_code", ["bn", "ta", "te", "kn", "ml", "gu", "pa", "or", "mr", "ur", "ar", "zh"])
    def test_scaffolded_nfc_idempotence(self, lang_code):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            plugin = get_plugin(lang_code)
            sample = "Sample text 123"
            assert plugin.normalize(plugin.normalize(sample)) == plugin.normalize(sample)
