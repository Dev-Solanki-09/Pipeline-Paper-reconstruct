"""
Legacy-font detection and transliteration for KrutiDev and Chanakya fonts.

Detects non-Unicode 8-bit Devanagari typesetting by font name or character frequency
heuristics, transliterates to standard Unicode Devanagari, and flags pages needing OCR.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

_FONTMAPS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "fontmaps"
_CACHED_FONTMAPS: dict[str, dict] = {}


def _get_fontmap(font_id: str) -> dict:
    if font_id in _CACHED_FONTMAPS:
        return _CACHED_FONTMAPS[font_id]

    json_path = _FONTMAPS_DIR / f"{font_id}.json"
    if not json_path.is_file():
        # Fallback to krutidev010
        json_path = _FONTMAPS_DIR / "krutidev010.json"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    _CACHED_FONTMAPS[font_id] = data
    return data


# Characteristic KrutiDev/Chanakya digraphs & tokens
_LEGACY_PATTERNS = [
    "[k", "?k", "Fk", "/k", "Hk", "'k", "\"k", "{k", "=k", ">k",
    "vk", "bZ", "ks", "kS", "AA", "Hkkjr", "fd", "f[k", "fx",
]


def detect_legacy_font(text: str, font_name: str | None = None) -> tuple[str | None, float]:
    """
    Detect whether text was rendered with a legacy 8-bit Devanagari font.

    Returns:
        tuple of (font_id or None, confidence_score between 0.0 and 1.0)
    """
    if font_name:
        fname = font_name.lower()
        if any(alias in fname for alias in ["kruti", "devlys"]):
            return "krutidev010", 0.99
        if any(alias in fname for alias in ["chanakya", "walkman"]):
            return "chanakya", 0.99

    if not text:
        return None, 0.0

    # Frequency heuristic on raw text
    matches = sum(1 for pat in _LEGACY_PATTERNS if pat in text)
    # Check for atypical punctuation-letter combinations like '[k', '?k', '/k'
    tokens = text.split()
    if not tokens:
        return None, 0.0

    score = min(1.0, (matches * 0.2) + (text.count("k") / max(1, len(text)) * 0.5))

    # Reject if it looks like standard English prose
    english_words = {"the", "and", "is", "of", "in", "to", "calculate", "velocity", "total", "body"}
    words = {w.lower() for w in re.findall(r"\b[a-zA-Z]+\b", text)}
    if len(words.intersection(english_words)) >= 2:
        return None, 0.1

    if matches >= 2 or (matches >= 1 and score >= 0.5):
        return "krutidev010", max(0.6, score)

    return None, score


def needs_ocr_for_script(text: str, font_name: str | None = None) -> bool:
    """
    Determine if the text contains garbled or unmapped glyph bytes requiring OCR fallback.
    """
    if not text:
        return False

    # Check for unmapped high-ASCII / control bytes (0x80 to 0x9F)
    garbled_count = sum(1 for ch in text if 0x80 <= ord(ch) <= 0x9F or 0x00 <= ord(ch) <= 0x08)
    if garbled_count > 0:
        return True

    return False


def convert_legacy_font(text: str, font_name: str | None = None) -> str:
    """
    Transliterate legacy-encoded text (KrutiDev / Chanakya) into Unicode Devanagari.
    """
    if not text:
        return text

    font_id, conf = detect_legacy_font(text, font_name)
    if not font_id:
        font_id = "krutidev010"

    fmap = _get_fontmap(font_id)
    digraphs: dict[str, str] = fmap.get("digraphs", {})
    singles: dict[str, str] = fmap.get("singles", {})

    # Pre-process: handle prefix 'f' (chhoti i matra 'ि')
    # In KrutiDev, 'f' comes before the consonant/cluster, e.g. 'fd' -> 'd' + 'f' -> कि
    # Handle 'f' followed by digraph or single consonant
    result_chars: list[str] = []
    i = 0
    chars = text

    # First pass: rearrange prefix 'f' to follow the consonant/cluster
    rearranged = []
    idx = 0
    while idx < len(chars):
        if chars[idx] == "f" and idx + 1 < len(chars):
            # Check if next is a digraph
            next_two = chars[idx + 1:idx + 3]
            if next_two in digraphs:
                rearranged.append(next_two)
                rearranged.append("\u093F")
                idx += 3
                continue
            elif chars[idx + 1] in singles or chars[idx + 1].isalpha():
                rearranged.append(chars[idx + 1])
                rearranged.append("\u093F")
                idx += 2
                continue
        rearranged.append(chars[idx])
        idx += 1

    temp_text = "".join(rearranged)

    # Second pass: replace digraphs
    for legacy, unicode_char in sorted(digraphs.items(), key=lambda x: len(x[0]), reverse=True):
        temp_text = temp_text.replace(legacy, unicode_char)

    # Third pass: replace single characters
    converted = []
    for ch in temp_text:
        if ch == "Z":  # KrutiDev reph
            converted.append("र्")
        elif ch in singles:
            converted.append(singles[ch])
        else:
            converted.append(ch)

    res = "".join(converted)

    # Fix reph positioning: in Devanagari, 'र्' comes BEFORE the consonant, but in KrutiDev 'Z' came after
    # e.g. क + र् -> र्क
    res = re.sub(r"([\u0900-\u097F])र्", r"र्\1", res)

    # Unicode NFC normalization
    return unicodedata.normalize("NFC", res)


# Alias for backward compatibility
transliterate_legacy_font = convert_legacy_font
