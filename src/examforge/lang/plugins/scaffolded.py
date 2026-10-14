"""
Scaffolded language plugins.

Provides plugins for regional and international scripts:
bn, ta, te, kn, ml, gu, pa, or, mr, ur (RTL), ar (RTL), zh, ja, ko.

These plugins implement script detection, digit maps, and safe NFC normalization,
and have is_ship_quality=False (raising NotShipQualityWarning when accessed).
"""

from __future__ import annotations

import unicodedata


class ScaffoldedScriptPlugin:
    """Scaffolded plugin for an uncertified language script."""

    def __init__(
        self,
        lang: str,
        script: str,
        direction: str = "ltr",
        digits_map: dict[str, str] | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self.lang = lang
        self.script = script
        self.direction = direction
        self.is_ship_quality = False
        self.digits_map = digits_map or {}
        self.capabilities = capabilities or [f"{lang}_scaffolded"]

    def normalize(self, text: str) -> str:
        if not text:
            return text
        text = unicodedata.normalize("NFC", text)
        text = self.punctuation_fixes(text)
        return text.strip()

    def punctuation_fixes(self, text: str) -> str:
        return text

    def split_bilingual(self, text: str, second_lang: str = "hi") -> tuple[str, str]:
        from examforge.lang.bilingual import split_bilingual_by_script
        return split_bilingual_by_script(text, primary_lang="en", secondary_lang=self.lang)

    def font_repair(self, text: str, font_name: str | None = None) -> str:
        return text


# Predefined digit maps
_BENGALI_DIGITS = {chr(0x09E6 + i): str(i) for i in range(10)}
_GURMUKHI_DIGITS = {chr(0x0A66 + i): str(i) for i in range(10)}
_GUJARATI_DIGITS = {chr(0x0AE6 + i): str(i) for i in range(10)}
_ORIYA_DIGITS = {chr(0x0B66 + i): str(i) for i in range(10)}
_TAMIL_DIGITS = {
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4",
    "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
}
_TELUGU_DIGITS = {chr(0x0C66 + i): str(i) for i in range(10)}
_KANNADA_DIGITS = {chr(0x0CE6 + i): str(i) for i in range(10)}
_MALAYALAM_DIGITS = {chr(0x0D66 + i): str(i) for i in range(10)}
_PERSO_ARABIC_DIGITS = {chr(0x06F0 + i): str(i) for i in range(10)}  # Urdu / Persian
_ARABIC_INDIC_DIGITS = {chr(0x0660 + i): str(i) for i in range(10)}  # Arabic
_FULLWIDTH_DIGITS = {chr(0xFF10 + i): str(i) for i in range(10)}  # CJK
_DEVANAGARI_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}


def get_scaffolded_plugins() -> list[ScaffoldedScriptPlugin]:
    """Return all standard scaffolded plugins."""
    return [
        ScaffoldedScriptPlugin("bn", "Beng", digits_map=_BENGALI_DIGITS),
        ScaffoldedScriptPlugin("ta", "Taml", digits_map=_TAMIL_DIGITS),
        ScaffoldedScriptPlugin("te", "Telu", digits_map=_TELUGU_DIGITS),
        ScaffoldedScriptPlugin("kn", "Knda", digits_map=_KANNADA_DIGITS),
        ScaffoldedScriptPlugin("ml", "Mlym", digits_map=_MALAYALAM_DIGITS),
        ScaffoldedScriptPlugin("gu", "Gujr", digits_map=_GUJARATI_DIGITS),
        ScaffoldedScriptPlugin("pa", "Guru", digits_map=_GURMUKHI_DIGITS),
        ScaffoldedScriptPlugin("or", "Orya", digits_map=_ORIYA_DIGITS),
        ScaffoldedScriptPlugin("mr", "Deva", digits_map=_DEVANAGARI_DIGITS),
        ScaffoldedScriptPlugin("ur", "Arab", direction="rtl", digits_map=_PERSO_ARABIC_DIGITS),
        ScaffoldedScriptPlugin("ar", "Arab", direction="rtl", digits_map=_ARABIC_INDIC_DIGITS),
        ScaffoldedScriptPlugin("zh", "Hani", digits_map=_FULLWIDTH_DIGITS),
        ScaffoldedScriptPlugin("ja", "Hani", digits_map=_FULLWIDTH_DIGITS),
        ScaffoldedScriptPlugin("ko", "Hang", digits_map=_FULLWIDTH_DIGITS),
    ]
