"""Figure resolution policy and scale-class taxonomy.

Enforces:
- Clamped native DPI: render crops at dpi = clamp(target_px / bbox_h, min_dpi, native_dpi).
- Never upscale beyond native_dpi.
- Standard scale classes for STEM exams.
"""

from __future__ import annotations


def compute_target_dpi(
    bbox_w: float,
    bbox_h: float,
    target_px: int = 1200,
    min_dpi: int = 150,
    native_dpi: int = 300,
) -> int:
    """Compute target rendering DPI clamped by native DPI.

    Never upscales beyond native_dpi.
    """
    effective_h = max(bbox_h, 1.0)
    # Target DPI based on desired pixel dimensions (72 pt per inch)
    desired_dpi = (target_px / effective_h) * 72.0
    clamped_dpi = int(min(max(desired_dpi, min_dpi), native_dpi))
    return clamped_dpi


def classify_scale_class(width_px: int, height_px: int) -> str:
    """Map figure dimensions to canonical STEM diagram scale taxonomy:

    - img-inline: tiny inline icons or small symbols (height <= 40)
    - img-opt: option-level diagrams (height <= 65, width <= 220)
    - img-sm: small diagrams (height <= 120, width <= 240)
    - img-wide: wide panoramic graphs or circuits (width/height > 1.8)
    - img-lg: large multi-part diagrams (height >= 280)
    - img-md: standard medium diagrams (default)
    """
    if height_px <= 40:
        return "img-inline"
    if height_px <= 65 and width_px <= 220:
        return "img-opt"
    if height_px <= 120 and width_px <= 240:
        return "img-sm"
    if width_px / max(height_px, 1) > 1.8 and height_px <= 180:
        return "img-wide"
    if height_px >= 280 or width_px >= 340:
        return "img-lg"
    return "img-md"
