"""Legacy adapter for R13: render_check (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.packaged_output_check import (
    PAGE_WRAPPER_PATTERNS,
    _check_latex_syntax,
    _validate_image_payload,
    validate_packaged_output,
    validate_packaged_output as validate_render_check,
)

__all__ = [
    "PAGE_WRAPPER_PATTERNS",
    "_check_latex_syntax",
    "_validate_image_payload",
    "validate_packaged_output",
    "validate_render_check",
]
