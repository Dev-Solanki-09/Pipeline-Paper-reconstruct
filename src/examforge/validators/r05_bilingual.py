"""Legacy adapter for R05: en_hi_pairs_complete (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.language_consistency import validate_language_consistency

validate_bilingual_pairs = validate_language_consistency

__all__ = ["validate_bilingual_pairs"]
