"""Legacy adapter for R01: no_headers_footers_page_numbers (Phase O4.2)."""

from __future__ import annotations

from examforge.validators.furniture_branding import validate_furniture_branding

validate_no_furniture = validate_furniture_branding

__all__ = ["validate_no_furniture"]
