"""Legacy adapter for R02: no_brand_text_or_logo (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.furniture_branding import validate_furniture_branding

validate_no_branding = validate_furniture_branding

__all__ = ["validate_no_branding"]
