"""ExamForge clean package: geometry, illumination, watermark median, furniture, and branding."""

from __future__ import annotations

from examforge.clean.branding import (
    is_false_positive_trap,
    scrub_branding_blocks,
)
from examforge.clean.furniture import (
    detect_page_numbers_script_aware,
    find_repeating_furniture_blocks,
    is_protected_content,
)
from examforge.clean.geometry import (
    correct_orientation,
    deskew_image,
    detect_orientation,
    detect_skew_angle,
    split_two_up_spread,
)
from examforge.clean.illumination import (
    calculate_ssim,
    flatten_illumination,
)
from examforge.clean.watermark_median import (
    calculate_residual_correlation,
    estimate_watermark_median,
    remove_baked_watermark,
)

__all__ = [
    "calculate_residual_correlation",
    "calculate_ssim",
    "correct_orientation",
    "deskew_image",
    "detect_orientation",
    "detect_page_numbers_script_aware",
    "detect_skew_angle",
    "estimate_watermark_median",
    "find_repeating_furniture_blocks",
    "flatten_illumination",
    "is_false_positive_trap",
    "is_protected_content",
    "remove_baked_watermark",
    "scrub_branding_blocks",
    "split_two_up_spread",
]
