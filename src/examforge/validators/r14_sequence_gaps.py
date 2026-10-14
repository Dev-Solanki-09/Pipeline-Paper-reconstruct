"""Legacy adapter for R14: sequence_gaps (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.structure_integrity import (
    validate_structure_integrity,
    validate_structure_integrity as validate_sequence_gaps,
)

__all__ = ["validate_sequence_gaps", "validate_structure_integrity"]
