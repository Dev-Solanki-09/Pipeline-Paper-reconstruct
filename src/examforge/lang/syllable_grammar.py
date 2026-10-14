"""Devanagari syllable-grammar validation (Phase O7.4).

Validates Devanagari script character sequences against classical phonotactic
and orthographic rules to catch character-level OCR substitutions and malformed
ligatures before downstream processing.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Unicode ranges for Devanagari (U+0900 to U+097F)
# Independent Vowels
_INDEPENDENT_VOWELS = set(
    "\u0904\u0905\u0906\u0907\u0908\u0909\u090A\u090B\u090C\u090D\u090E\u090F"
    "\u0910\u0911\u0912\u0913\u0914\u0960\u0961\u0972\u0973\u0974\u0975\u0976\u0977"
)

# Consonants
_CONSONANTS = set(
    "\u0915\u0916\u0917\u0918\u0919"
    "\u091A\u091B\u091C\u091D\u091E"
    "\u091F\u0920\u0921\u0922\u0923"
    "\u0924\u0925\u0926\u0927\u0928"
    "\u0929\u092A\u092B\u092C\u092D\u092E"
    "\u092F\u0930\u0931\u0932\u0933\u0934\u0935\u0936\u0937\u0938\u0939"
    "\u0958\u0959\u095A\u095B\u095C\u095D\u095E\u095F"
)

# Dependent Vowel Signs (Matras)
_MATRAS = set(
    "\u093E\u093F\u0940\u0941\u0942\u0943\u0944\u0945\u0946\u0947\u0948"
    "\u0949\u094A\u094B\u094C\u094E\u094F\u0955\u0956\u0957\u0962\u0963"
)

# Virama (Halant)
_VIRAMA = "\u094D"

# Nukta
_NUKTA = "\u093C"

# Modifiers (Anusvara, Chandrabindu, Visarga)
_MODIFIERS = set("\u0901\u0902\u0903")


class SyllableViolation(NamedTuple):
    offset: int
    rule: str
    substring: str
    description: str


def validate_devanagari_syllables(text: str) -> list[SyllableViolation]:
    """Check text for phonotactic Devanagari syllable grammar violations.

    Catches:
    1. Orphan matras at start of word or after whitespace/punctuation.
    2. Multiple consecutive matras on a consonant.
    3. Matra attached to an independent vowel (e.g. अ + ी).
    4. Orphan virama (halant) at start of word.
    5. Consecutive viramas.
    6. Repeated nuktas.
    """
    if not text:
        return []

    violations: list[SyllableViolation] = []
    n = len(text)

    for i, ch in enumerate(text):
        # 1. Orphan matra
        if ch in _MATRAS:
            if i == 0 or text[i - 1].isspace() or text[i - 1] in ".,;:!?-()[]{}\"'/|॥।":
                violations.append(
                    SyllableViolation(
                        offset=i,
                        rule="orphan_matra",
                        substring=text[max(0, i - 1) : min(n, i + 2)],
                        description=f"Orphan dependent vowel sign '{ch}' at position {i} without preceding base.",
                    )
                )
            elif text[i - 1] in _INDEPENDENT_VOWELS:
                violations.append(
                    SyllableViolation(
                        offset=i,
                        rule="matra_on_independent_vowel",
                        substring=text[i - 1 : i + 1],
                        description=f"Dependent vowel sign '{ch}' attached to independent vowel '{text[i-1]}'.",
                    )
                )
            elif text[i - 1] in _MATRAS:
                violations.append(
                    SyllableViolation(
                        offset=i,
                        rule="consecutive_matras",
                        substring=text[i - 1 : i + 1],
                        description=f"Conflicting consecutive vowel signs '{text[i-1]}' and '{ch}'.",
                    )
                )

        # 2. Orphan or duplicate virama
        elif ch == _VIRAMA:
            if i == 0 or text[i - 1].isspace() or text[i - 1] not in _CONSONANTS:
                if i > 0 and text[i - 1] == _VIRAMA:
                    violations.append(
                        SyllableViolation(
                            offset=i,
                            rule="duplicate_virama",
                            substring=text[i - 1 : i + 1],
                            description=f"Duplicate virama at position {i}.",
                        )
                    )
                elif i == 0 or text[i - 1].isspace():
                    violations.append(
                        SyllableViolation(
                            offset=i,
                            rule="orphan_virama",
                            substring=text[max(0, i - 1) : min(n, i + 2)],
                            description=f"Orphan virama at start of word (position {i}).",
                        )
                    )

        # 3. Duplicate nukta
        elif ch == _NUKTA:
            if i > 0 and text[i - 1] == _NUKTA:
                violations.append(
                    SyllableViolation(
                        offset=i,
                        rule="duplicate_nukta",
                        substring=text[i - 1 : i + 1],
                        description=f"Duplicate nukta at position {i}.",
                    )
                )

    return violations


def sanitize_devanagari_syllables(text: str) -> tuple[str, int]:
    """Correct trivial mechanical syllable errors while preserving semantics.

    Returns:
        (sanitized_text, fix_count)
    """
    if not text:
        return text, 0

    fix_count = 0
    orig = text

    # Remove orphan matra at start of word
    cleaned = re.sub(r"(^|[\s.,;:()\[\]\"'/])[\u093E-\u094C\u0962\u0963]+", r"\1", text)
    if cleaned != text:
        fix_count += 1
        text = cleaned

    # Collapse duplicate viramas
    cleaned = re.sub(r"\u094D{2,}", "\u094D", text)
    if cleaned != text:
        fix_count += 1
        text = cleaned

    # Collapse duplicate nuktas
    cleaned = re.sub(r"\u093C{2,}", "\u093C", text)
    if cleaned != text:
        fix_count += 1
        text = cleaned

    return text, fix_count
