"""Degradation engine for synthetic exam papers (L0 to L4).

Simulates real-world scanning, photocopying, and phone capture artifacts
deterministically using Pillow and NumPy.
"""

from __future__ import annotations

import io
import math
import random
from typing import Literal

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


DegradeLevel = Literal["L0", "L1", "L2", "L3", "L4"]


def apply_skew(image: Image.Image, angle_deg: float) -> Image.Image:
    """Rotate image by angle_deg with white background fill."""
    if abs(angle_deg) < 1e-3:
        return image
    return image.rotate(angle_deg, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=(255, 255, 255))


def apply_gaussian_noise(image: Image.Image, sigma: float, rng: np.random.Generator) -> Image.Image:
    """Add zero-mean Gaussian noise with standard deviation sigma."""
    if sigma <= 0:
        return image
    arr = np.array(image, dtype=np.float32)
    noise = rng.normal(0, sigma, arr.shape)
    noisy_arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy_arr)


def apply_jpeg_compression(image: Image.Image, quality: int) -> Image.Image:
    """Simulate lossy JPEG artifacts."""
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).copy()


def apply_shadow_gradient(image: Image.Image, intensity: float = 0.35, rng: np.random.Generator | None = None) -> Image.Image:
    """Simulate uneven illumination or book-spine shadow across the page."""
    w, h = image.size
    arr = np.array(image, dtype=np.float32)

    # Spine shadow usually runs vertically on one side (left or right)
    side = 0 if (rng and rng.random() < 0.5) else 1
    x_coords = np.linspace(0, 1, w, dtype=np.float32)
    if side == 1:
        x_coords = 1.0 - x_coords

    # Exponential shadow falloff from edge
    shadow = 1.0 - intensity * np.exp(-x_coords * 4.0)
    shadow_2d = np.tile(shadow, (h, 1))

    if arr.ndim == 3:
        shadow_3d = np.expand_dims(shadow_2d, axis=-1)
    else:
        shadow_3d = shadow_2d

    darkened = np.clip(arr * shadow_3d, 0, 255).astype(np.uint8)
    return Image.fromarray(darkened)


def apply_fold_line(image: Image.Image, y_fraction: float = 0.5, thickness: int = 3) -> Image.Image:
    """Simulate horizontal fold line artifact from paper folding."""
    w, h = image.size
    arr = np.array(image, dtype=np.float32)
    y_center = int(h * y_fraction)
    for dy in range(-thickness, thickness + 1):
        y = y_center + dy
        if 0 <= y < h:
            factor = 0.75 + 0.25 * (abs(dy) / max(1, thickness))
            arr[y, :, :] *= factor

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_vignette(image: Image.Image, strength: float = 0.4) -> Image.Image:
    """Simulate smartphone camera lens vignette darkening at corners."""
    w, h = image.size
    arr = np.array(image, dtype=np.float32)

    y, x = np.ogrid[:h, :w]
    cx, cy = w / 2.0, h / 2.0
    # Radial distance normalized by max corner distance
    r_max = math.hypot(cx, cy)
    dist = np.hypot(x - cx, y - cy) / r_max

    vignette = 1.0 - strength * (dist ** 2)
    vignette = np.clip(vignette, 0.0, 1.0)
    if arr.ndim == 3:
        vignette = np.expand_dims(vignette, axis=-1)

    return Image.fromarray(np.clip(arr * vignette, 0, 255).astype(np.uint8))


def apply_perspective_warp(image: Image.Image, max_offset_px: int = 15, rng: random.Random | None = None) -> Image.Image:
    """Apply mild perspective quadrilateral warp simulating hand-held phone angle."""
    w, h = image.size
    r = rng or random.Random()
    dx1 = r.uniform(-max_offset_px, max_offset_px)
    dy1 = r.uniform(-max_offset_px, max_offset_px)
    dx2 = r.uniform(-max_offset_px, max_offset_px)
    dy2 = r.uniform(-max_offset_px, max_offset_px)

    # Quad transform
    src_quad = [
        0, 0,
        0, h,
        w, h,
        w, 0
    ]
    coeffs = [
        dx1, dy1,
        -dx1, h + dy2,
        w - dx2, h - dy1,
        w + dx2, -dy2
    ]
    # Pillow transform QUAD requires 8-tuple bounding quadrilateral in source coordinates
    return image.transform(
        (w, h),
        Image.Transform.QUAD,
        (
            0 - dx1, 0 - dy1,
            0 - dx2, h + dy1,
            w + dx1, h + dy2,
            w + dx2, 0 - dy2,
        ),
        resample=Image.Resampling.BILINEAR,
        fillcolor=(255, 255, 255),
    )


def degrade_page(
    image: Image.Image,
    level: DegradeLevel = "L0",
    seed: int = 42,
) -> Image.Image:
    """
    Apply reproducible, seeded degradation at specified tier:
      L0: Clean digital (original)
      L1: Rasterized at 150 DPI (clean raster scan)
      L2: Mild scan (skew ±1.5°, blur σ <= 1, JPEG q70, noise)
      L3: Degraded scan (L2 + uneven illumination shadow + fold lines)
      L4: Smartphone capture (L3 + perspective quad warp + vignette + JPEG q55)
    """
    if level == "L0":
        return image.copy()

    py_rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    im = image.copy()

    if level == "L1":
        # Pure 150 DPI rasterization simulation
        # High quality re-save without blur or distortion
        return apply_jpeg_compression(im, quality=95)

    if level in ("L2", "L3", "L4"):
        # 1. Skew ±1.5°
        skew_deg = py_rng.uniform(-1.5, 1.5)
        im = apply_skew(im, skew_deg)

        # 2. Gaussian blur sigma <= 1
        im = im.filter(ImageFilter.GaussianBlur(radius=py_rng.uniform(0.4, 0.8)))

        # 3. Sensor / Gaussian noise
        im = apply_gaussian_noise(im, sigma=8.0, rng=np_rng)

        # 4. JPEG q70
        im = apply_jpeg_compression(im, quality=70)

    if level in ("L3", "L4"):
        # 5. Uneven book-spine / lighting shadow
        im = apply_shadow_gradient(im, intensity=0.25, rng=np_rng)

        # 6. Fold line
        im = apply_fold_line(im, y_fraction=py_rng.uniform(0.4, 0.6), thickness=2)

    if level == "L4":
        # 7. Perspective quad warp
        im = apply_perspective_warp(im, max_offset_px=14, rng=py_rng)

        # 8. Vignette shading
        im = apply_vignette(im, strength=0.35)

        # 9. Heavier JPEG compression
        im = apply_jpeg_compression(im, quality=55)

    return im
