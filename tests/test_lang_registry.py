"""Tests for ScriptPlugin protocol, registry, and script detection."""

from __future__ import annotations

import warnings
import pytest

from examforge.lang.registry import (
    NotShipQualityWarning,
    ScriptPlugin,
    detect_lang,
    detect_script,
    get_plugin,
    list_supported_languages,
    register_plugin,
    resolve_plugins_for_profile,
)
from examforge.profiles.schema import ExamProfile, LanguageProfileConfig


def test_registry_has_standard_plugins():
    supported = list_supported_languages()
    assert "en" in supported
    assert "hi" in supported
    # Scaffolded plugins
    for code in ["bn", "ta", "te", "kn", "ml", "gu", "pa", "or", "mr", "ur", "ar", "zh", "ja", "ko"]:
        assert code in supported


def test_ship_quality_plugins_do_not_warn():
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        en_plugin = get_plugin("en")
        hi_plugin = get_plugin("hi")
        assert en_plugin.is_ship_quality is True
        assert hi_plugin.is_ship_quality is True
        # Check no NotShipQualityWarning was raised
        ship_warnings = [w for w in recorded if issubclass(w.category, NotShipQualityWarning)]
        assert len(ship_warnings) == 0


def test_scaffolded_plugin_warns():
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        bn_plugin = get_plugin("bn")
        assert bn_plugin.is_ship_quality is False
        ship_warnings = [w for w in recorded if issubclass(w.category, NotShipQualityWarning)]
        assert len(ship_warnings) >= 1
        assert "scaffolded" in str(ship_warnings[0].message).lower()


def test_script_detection_by_unicode_range():
    assert detect_script("Hello world, this is a test.") == "Latn"
    assert detect_script("यह एक हिंदी वाक्य है।") == "Deva"
    assert detect_script("এটি একটি বাংলা বাক্য।") == "Beng"
    assert detect_script("இது ஒரு தமிழ் வாக்கியம்.") == "Taml"
    assert detect_script("ఇది ఒక తెలుగు వాక్యము.") == "Telu"
    assert detect_script("ಇದು ಕನ್ನಡ ವಾಕ್ಯ.") == "Knda"
    assert detect_script("ഇത് ഒരു മലയാളം വാചകമാണ്.") == "Mlym"
    assert detect_script("આ એક ગુજરાતી વાક્ય છે.") == "Gujr"
    assert detect_script("ਇਹ ਇੱਕ ਪੰਜਾਬੀ ਵਾਕ ਹੈ।") == "Guru"
    assert detect_script("ଏହା ଏକ ଓଡ଼ିଆ ବାକ୍ୟ।") == "Orya"
    assert detect_script("یہ ایک اردو جملہ ہے۔") == "Arab"
    assert detect_script("هذا نص عربي.") == "Arab"
    assert detect_script("这是一个中文句子。") == "Hani"


def test_detect_lang_fallback():
    assert detect_lang("Hello world") == "en"
    assert detect_lang("नमस्ते दुनिया") == "hi"
    assert detect_lang("এটি একটি পরীক্ষা") == "bn"
    assert detect_lang("یہ ایک امتحان ہے") == "ur"


def test_resolve_plugins_for_profile():
    spec = ExamProfile(
        id="test-profile",
        name="Test Profile",
        languages=[
            LanguageProfileConfig(code="en", script="Latn"),
            LanguageProfileConfig(code="hi", script="Deva"),
        ],
    )
    plugins = resolve_plugins_for_profile(spec)
    assert len(plugins) == 2
    assert plugins[0].lang == "en"
    assert plugins[1].lang == "hi"


def test_custom_plugin_registration():
    class DummyPlugin:
        lang = "xx"
        script = "Dummy"
        direction = "ltr"
        is_ship_quality = True
        capabilities = ["dummy"]
        digits_map = {}

        def normalize(self, text: str) -> str:
            return text.strip()

        def punctuation_fixes(self, text: str) -> str:
            return text

        def split_bilingual(self, text: str, second_lang: str = "hi") -> tuple[str, str]:
            return text, ""

        def font_repair(self, text: str, font_name: str | None = None) -> str:
            return text

    register_plugin(DummyPlugin())
    p = get_plugin("xx")
    assert p.lang == "xx"
    assert p.normalize("  hello  ") == "hello"
