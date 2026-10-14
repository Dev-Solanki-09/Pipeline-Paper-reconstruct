"""Legacy adapter for R15: structure_consistency (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.structure_integrity import (
    SUBPART_LABEL_RE,
    _get_subpart_key,
    validate_structure_integrity,
    validate_structure_integrity as validate_structure_consistency,
)

__all__ = [
    "SUBPART_LABEL_RE",
    "_get_subpart_key",
    "validate_structure_consistency",
    "validate_structure_integrity",
]
