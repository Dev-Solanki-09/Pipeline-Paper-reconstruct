"""Black-border removal for scanned pages and cropped figures."""

from __future__ import annotations

import numpy as np
from PIL import Image


def remove_black_borders(
    image: Image.Image,
    dark_threshold: int = 35,
    line_density: float = 0.6,
    max_trim_fraction: float = 0.25,
) -> tuple[Image.Image, tuple[int, int]]:
    """Detect and remove dark/black scan borders around an image.

    Args:
        image: PIL Image (RGB, L, etc.)
        dark_threshold: Pixel brightness below which is considered black/ink
        line_density: Fraction of pixels along a border line that must be dark
        max_trim_fraction: Maximum fraction of width/height allowed to trim on any edge

    Returns:
        tuple of (cleaned_image, (crop_x_offset, crop_y_offset))
    """
    gray = image.convert("L")
    arr = np.array(gray)
    h, w = arr.shape

    max_x_trim = int(w * max_trim_fraction)
    max_y_trim = int(h * max_trim_fraction)

    # Detect top trim
    top = 0
    while top < max_y_trim:
        row = arr[top, :]
        if np.mean(row < dark_threshold) >= line_density:
            top += 1
        else:
            break

    # Detect bottom trim
    bottom = 0
    while bottom < max_y_trim:
        row = arr[h - 1 - bottom, :]
        if np.mean(row < dark_threshold) >= line_density:
            bottom += 1
        else:
            break

    # Detect left trim
    left = 0
    while left < max_x_trim:
        col = arr[:, left]
        if np.mean(col < dark_threshold) >= line_density:
            left += 1
        else:
            break

    # Detect right trim
    right = 0
    while right < max_x_trim:
        col = arr[:, w - 1 - right]
        if np.mean(col < dark_threshold) >= line_density:
            right += 1
        else:
            break

    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return image, (0, 0)

    new_w = w - left - right
    new_h = h - top - bottom
    if new_w < 10 or new_h < 10:
        return image, (0, 0)

    cropped = image.crop((left, top, w - right, h - bottom))
    return cropped, (left, top)
