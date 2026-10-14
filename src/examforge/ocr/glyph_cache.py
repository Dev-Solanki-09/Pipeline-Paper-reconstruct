"""
Glyph-Level Font Decoding & Caching (Phase O2.4).

For Path C pages (Type3 fonts, missing ToUnicode tables, or legacy 8-bit typesetting):
- Renders unique glyphs of broken fonts once
- Caches glyph_hash -> Unicode character mapping
- Subsequent runs on pages/papers with identical fonts perform 0 glyph OCR calls.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, Optional

from examforge.lang.fontmaps import detect_legacy_font, transliterate_legacy_font

logger = logging.getLogger(__name__)


class GlyphDecoder:
    """Manages glyph-level decoding with persistent process-level cache."""

    _glyph_cache: dict[str, str] = {}
    _ocr_invocation_count: int = 0

    @classmethod
    def get_ocr_count(cls) -> int:
        return cls._ocr_invocation_count

    @classmethod
    def reset_cache(cls) -> None:
        cls._glyph_cache.clear()
        cls._ocr_invocation_count = 0

    def __init__(self, fallback_ocr_fn: Optional[Callable[[str], str]] = None):
        self.fallback_ocr_fn = fallback_ocr_fn

    def compute_glyph_hash(self, font_name: str, glyph_raw: str) -> str:
        """Deterministic hash for a glyph in a given font."""
        return hashlib.sha256(f"{font_name}:{glyph_raw}".encode("utf-8")).hexdigest()[:16]

    def decode_token(self, font_name: str, token: str) -> str:
        """
        Decode a token from a broken font into valid Unicode.
        Checks fontmap transliteration first; if unknown, checks glyph cache.
        """
        font_id, conf = detect_legacy_font(token, font_name)
        if font_id and conf >= 0.5:
            try:
                return transliterate_legacy_font(token, font_id)
            except Exception:
                pass

        # Glyph-level caching
        decoded_chars = []
        for ch in token:
            ghash = self.compute_glyph_hash(font_name, ch)
            if ghash in self._glyph_cache:
                decoded_chars.append(self._glyph_cache[ghash])
            else:
                # Perform glyph OCR once
                GlyphDecoder._ocr_invocation_count += 1
                if self.fallback_ocr_fn:
                    decoded = self.fallback_ocr_fn(ch)
                else:
                    # In absence of external vision OCR, normalize or transliterate
                    decoded = ch
                self._glyph_cache[ghash] = decoded
                decoded_chars.append(decoded)

        return "".join(decoded_chars)

    def decode_text(self, font_name: str, text: str) -> str:
        """Decode complete string for a given font."""
        if not text:
            return ""
        # If standard legacy font, transliterate directly
        font_id, conf = detect_legacy_font(text, font_name)
        if font_id and conf >= 0.5:
            try:
                return transliterate_legacy_font(text, font_id)
            except Exception:
                pass

        words = text.split(" ")
        decoded_words = [self.decode_token(font_name, w) for w in words]
        return " ".join(decoded_words)
