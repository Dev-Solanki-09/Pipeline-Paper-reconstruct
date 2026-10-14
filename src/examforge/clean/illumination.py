"""Illumination flattening via background estimation and flat-field division."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def flatten_illumination(
    image: Image.Image | np.ndarray,
    kernel_size: int = 25,
) -> Image.Image:
    """Flatten uneven shadows and vignetting via background estimation and division."""
    pil_im = image if isinstance(image, Image.Image) else Image.fromarray(image)
    gray = pil_im.convert("L")
    w, h = gray.size

    # Estimate background: downsample to ~1/8 scale, heavy blur, and scale back up
    scale_factor = 8
    small_w = max(10, w // scale_factor)
    small_h = max(10, h // scale_factor)
    small = gray.resize((small_w, small_h), resample=Image.Resampling.BOX)

    # Max filter followed by heavy blur estimates background white level
    bg_small = small.filter(ImageFilter.MaxFilter(size=5)).filter(ImageFilter.GaussianBlur(radius=kernel_size // 2))
    bg_full = bg_small.resize((w, h), resample=Image.Resampling.BILINEAR)

    arr = np.array(gray, dtype=np.float32)
    bg_arr = np.array(bg_full, dtype=np.float32)
    bg_arr = np.maximum(bg_arr, 15.0)  # Avoid division by zero

    # Flat-field division: normalize by estimated background
    # Scaled such that background becomes 255
    flattened = np.clip((arr / bg_arr) * 255.0, 0, 255).astype(np.uint8)

    return Image.fromarray(flattened)


def calculate_ssim(
    im1: np.ndarray,
    im2: np.ndarray,
    mask: np.ndarray | None = None,
) -> float:
    """Calculate Structural Similarity Index (SSIM) between two grayscale images."""
    arr1 = im1.astype(np.float64)
    arr2 = im2.astype(np.float64)

    if mask is not None:
        if np.sum(mask) == 0:
            return 1.0
        x = arr1[mask]
        y = arr2[mask]
    else:
        x = arr1.ravel()
        y = arr2.ravel()

    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2

    mu_x = np.mean(x)
    mu_y = np.mean(y)
    sigma_x_sq = np.var(x)
    sigma_y_sq = np.var(y)
    sigma_xy = np.mean((x - mu_x) * (y - mu_y))

    numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
    denominator = (mu_x ** 2 + mu_y ** 2 + c1) * (sigma_x_sq + sigma_y_sq + c2)

    if denominator == 0:
        return 1.0

    return float(numerator / denominator)
