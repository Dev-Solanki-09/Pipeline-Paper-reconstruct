"""Legacy adapter for R10: language_consistency (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.language_consistency import (
    DEVA_TO_WESTERN,
    LATIN_TOKEN_RE,
    NUM_RE,
    extract_invariant_tokens,
    validate_language_consistency,
)

__all__ = [
    "DEVA_TO_WESTERN",
    "NUM_RE",
    "LATIN_TOKEN_RE",
    "extract_invariant_tokens",
    "validate_language_consistency",
]
