"""Legacy adapter for R04: no_page_wrappers_or_breaks (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.packaged_output_check import validate_packaged_output

validate_continuous_flow = validate_packaged_output

__all__ = ["validate_continuous_flow"]
