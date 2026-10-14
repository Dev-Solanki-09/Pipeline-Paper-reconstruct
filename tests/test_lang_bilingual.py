"""Tests for N-language bilingual and multi-lingual text segmentation."""

from __future__ import annotations

import pytest

from examforge.lang.bilingual import (
    segment_multilingual_text,
    split_bilingual_by_script,
)
from examforge.profiles.schema import LanguageLayout


class TestBilingualSplit:
    def test_two_language_multiline(self):
        text = "Calculate the kinetic energy.\nगतिज ऊर्जा की गणना करें।"
        en, hi = split_bilingual_by_script(text, primary_lang="en", secondary_lang="hi")
        assert en == "Calculate the kinetic energy."
        assert hi == "गतिज ऊर्जा की गणना करें।"

    def test_slash_delimited_bilingual(self):
        text = "Option A / विकल्प A"
        en, hi = split_bilingual_by_script(text, primary_lang="en", secondary_lang="hi")
        assert en == "Option A"
        assert hi == "विकल्प A"

    def test_bilingual_with_bengali(self):
        text = "Find the electric flux.\nতড়িৎ ফ্লাক্স নির্ণয় কর।"
        en, bn = split_bilingual_by_script(text, primary_lang="en", secondary_lang="bn")
        assert en == "Find the electric flux."
        assert bn == "তড়িৎ ফ্লাক্স নির্ণয় কর।"

    def test_bilingual_with_tamil(self):
        text = "Calculate velocity.\nதிசைவேகத்தை கணக்கிடுக."
        en, ta = split_bilingual_by_script(text, primary_lang="en", secondary_lang="ta")
        assert en == "Calculate velocity."
        assert ta == "திசைவேகத்தை கணக்கிடுக."

    def test_sentence_level_inline_split(self):
        text = "State Ohm's law. ओम का नियम बताइए।"
        en, hi = split_bilingual_by_script(text, primary_lang="en", secondary_lang="hi")
        assert en == "State Ohm's law."
        assert hi == "ओम का नियम बताइए।"


class TestMultilingualSegmentation:
    def test_three_language_segmentation(self):
        text = (
            "What is velocity?\n"
            "वेग क्या है?\n"
            "বেগ কি?"
        )
        res = segment_multilingual_text(text, target_languages=["en", "hi", "bn"])
        assert "en" in res and res["en"] == "What is velocity?"
        assert "hi" in res and res["hi"] == "वेग क्या है?"
        assert "bn" in res and res["bn"] == "বেগ কি?"

    def test_slash_delimited_three_languages(self):
        text = "10 m/s / 10 मी/से / 10 মি/সে"
        res = segment_multilingual_text(text, target_languages=["en", "hi", "bn"])
        assert res.get("en") == "10 m/s"
        assert res.get("hi") == "10 मी/से"
        assert res.get("bn") == "10 মি/সে"

    def test_unilingual_text_maps_to_detected_lang(self):
        text = "Pure English text here."
        res = segment_multilingual_text(text, target_languages=["en", "hi"])
        assert res.get("en") == "Pure English text here."
        assert res.get("hi", "") == ""
