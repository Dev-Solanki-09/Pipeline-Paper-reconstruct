"""English language plugin (Ship Quality)."""

from __future__ import annotations

import re
import unicodedata


class EnglishPlugin:
    """English / Latin script plugin."""

    lang = "en"
    script = "Latn"
    direction = "ltr"
    is_ship_quality = True
    capabilities = ["english_normalizer", "ascii_clean"]
    digits_map = {str(i): str(i) for i in range(10)}

    def normalize(self, text: str) -> str:
        if not text:
            return text
        text = unicodedata.normalize("NFC", text)
        text = self.punctuation_fixes(text)
        return text.strip()

    def punctuation_fixes(self, text: str) -> str:
        if not text:
            return text
        # Normalize curved quotes and dashes
        text = text.replace("“", '"').replace("”", '"')
        text = text.replace("‘", "'").replace("’", "'")
        text = text.replace("–", "-").replace("—", "-")
        return text

    def split_bilingual(self, text: str, second_lang: str = "hi") -> tuple[str, str]:
        return text, ""

    def font_repair(self, text: str, font_name: str | None = None) -> str:
        return text
