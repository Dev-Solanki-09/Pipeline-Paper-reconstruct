"""Hindi / Devanagari language plugin (Ship Quality)."""

from __future__ import annotations

import re
import unicodedata

# Devanagari Unicode ranges (U+0900 to U+097F)
_DEVANAGARI_CHAR_RE = re.compile(r"[\u0900-\u097F]")


class HindiPlugin:
    """Hindi / Devanagari script plugin with NFC, danda and nukta composition."""

    lang = "hi"
    script = "Deva"
    direction = "ltr"
    is_ship_quality = True
    capabilities = [
        "hindi_normalizer",
        "devanagari_clean",
        "danda_normalize",
        "nukta_composition",
        "devanagari_digits",
    ]
    digits_map = {
        "०": "0",
        "१": "1",
        "२": "2",
        "३": "3",
        "४": "4",
        "५": "5",
        "६": "6",
        "७": "7",
        "८": "8",
        "९": "9",
    }

    def normalize(self, text: str) -> str:
        if not text:
            return text

        # 1. Unicode NFC normalization (composes decomposed nuktas and matras)
        text = unicodedata.normalize("NFC", text)

        # 2. Punctuation and danda fixes
        text = self.punctuation_fixes(text)

        # 3. Clean spurious ZWJ / ZWNJ at whitespace or boundaries
        text = re.sub(r"(?<=\s)[\u200C\u200D]+", "", text)
        text = re.sub(r"[\u200C\u200D]+(?=\s|$)", "", text)
        text = re.sub(r"^[\u200C\u200D]+", "", text)

        # 4. Devanagari syllable grammar sanitization (Phase O7.4)
        from examforge.lang.syllable_grammar import sanitize_devanagari_syllables
        text, _ = sanitize_devanagari_syllables(text)

        return text.strip()

    def validate_syllables(self, text: str):
        from examforge.lang.syllable_grammar import validate_devanagari_syllables
        return validate_devanagari_syllables(text)

    def punctuation_fixes(self, text: str) -> str:
        if not text:
            return text

        # Double pipe || preceded by Devanagari -> double danda ॥ (\u0965)
        text = re.sub(r"([\u0900-\u097F]\s*)\|\|", r"\1॥", text)

        # Single pipe | preceded by Devanagari -> danda । (\u0964)
        # Avoid changing math pipes e.g. |x| = 5 where | is preceded by space/start
        text = re.sub(r"([\u0900-\u097F]\s*)\|(?![\w|])", r"\1।", text)

        return text

    def split_bilingual(self, text: str, second_lang: str = "hi") -> tuple[str, str]:
        from examforge.lang.bilingual import split_bilingual_by_script
        return split_bilingual_by_script(text, primary_lang="en", secondary_lang="hi")

    def font_repair(self, text: str, font_name: str | None = None) -> str:
        from examforge.lang.fontmaps import convert_legacy_font
        return convert_legacy_font(text, font_name)
