"""Geometric restoration: orientation detection, deskew, and spread splitting."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _get_gray_array(image: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, Image.Image):
        return np.array(image.convert("L"))
    if isinstance(image, np.ndarray) and image.ndim == 3:
        return np.array(Image.fromarray(image).convert("L"))
    return image


def detect_orientation(image: Image.Image | np.ndarray) -> int:
    """Detect rotation angle (0, 90, 180, or 270) that rights horizontal text."""
    pil_im = image if isinstance(image, Image.Image) else Image.fromarray(image)
    w, h = pil_im.size

    # If already portrait, test 0 vs 180
    # If landscape, test 90 vs 270
    candidates = [0, 90, 180, 270]
    best_angle = 0
    best_score = -1.0

    # Downsample for fast orientation testing
    small = pil_im.resize((150, int(150 * h / max(1, w))), resample=Image.Resampling.BOX)

    for angle in candidates:
        rot = small.rotate(angle, expand=True, fillcolor=255)
        rw, rh = rot.size
        # Strongly prefer portrait orientations
        aspect_bonus = 1.3 if rh > rw else 0.7

        arr = np.array(rot.convert("L"))
        # Inverted ink mask
        ink = (255 - arr).astype(np.float32)
        # Horizontal projection profile
        h_proj = np.sum(ink, axis=1)
        # Peakiness score (variance of difference)
        diff = np.diff(h_proj)
        score = float(np.var(diff)) * aspect_bonus

        if score > best_score:
            best_score = score
            best_angle = angle

    return best_angle


def correct_orientation(image: Image.Image, angle: int) -> Image.Image:
    """Rotate image by detected orientation angle (0, 90, 180, 270)."""
    if angle % 360 == 0:
        return image
    return image.rotate(angle, expand=True, fillcolor=255)


def detect_skew_angle(
    image: Image.Image | np.ndarray,
    max_angle: float = 15.0,
    angle_step: float = 0.5,
) -> float:
    """Detect text baseline skew angle within [-max_angle, max_angle] using projection profile variance."""
    pil_im = image if isinstance(image, Image.Image) else Image.fromarray(image)
    w, h = pil_im.size

    # Downscale for performance
    target_w = 300
    scale = target_w / max(1, w)
    small = pil_im.resize((target_w, max(10, int(h * scale))), resample=Image.Resampling.BILINEAR)

    angles = np.arange(-max_angle, max_angle + angle_step, angle_step)
    best_angle = 0.0
    best_variance = -1.0

    for a in angles:
        rot = small.rotate(float(a), expand=False, fillcolor=255, resample=Image.Resampling.NEAREST)
        arr = np.array(rot.convert("L"))
        ink = (255 - arr).astype(np.float32)
        row_sums = np.sum(ink, axis=1)
        var = float(np.var(row_sums))
        if var > best_variance:
            best_variance = var
            best_angle = float(a)

    # Note: best_angle is the rotation applied that maximized row peaks,
    # so the skew in the original image is -best_angle.
    return -best_angle


def deskew_image(image: Image.Image, angle: float) -> Image.Image:
    """Deskew image by rotating by -angle."""
    if abs(angle) < 0.1:
        return image
    return image.rotate(-angle, expand=False, fillcolor=255, resample=Image.Resampling.BILINEAR)


def split_two_up_spread(
    image: Image.Image,
    gutter_x: int | None = None,
) -> tuple[Image.Image, Image.Image]:
    """Split a two-up landscape scan at the central gutter into left and right portrait pages."""
    w, h = image.size
    split_x = gutter_x if gutter_x is not None else w // 2

    left_box = (0, 0, split_x, h)
    right_box = (split_x, 0, w, h)

    left_page = image.crop(left_box)
    right_page = image.crop(right_box)

    return left_page, right_page
