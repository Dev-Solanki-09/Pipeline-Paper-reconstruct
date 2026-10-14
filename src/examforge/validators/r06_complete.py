"""Legacy adapter for R06: numbering_continuity (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.structure_integrity import validate_structure_integrity

validate_numbering_continuity = validate_structure_integrity

__all__ = ["validate_numbering_continuity"]
