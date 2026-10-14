"""Cross-page median estimation and removal of fixed-position baked watermarks."""

from __future__ import annotations

import numpy as np
from PIL import Image

from examforge.ir.schema import Issue, IssueSeverity


def estimate_watermark_median(
    pages: list[Image.Image],
    scale_factor: int = 4,
) -> np.ndarray | None:
    """Estimate fixed-position watermark layer as the per-pixel median across multiple pages at 1/4 scale."""
    if not pages or len(pages) < 2:
        return None

    w, h = pages[0].size
    small_w = max(20, w // scale_factor)
    small_h = max(20, h // scale_factor)

    arrays = []
    for p in pages:
        gray = p.convert("L")
        if gray.size != (small_w, small_h):
            gray = gray.resize((small_w, small_h), resample=Image.Resampling.BOX)
        arrays.append(np.array(gray, dtype=np.float32))

    stack = np.stack(arrays, axis=0)
    wm_small = np.median(stack, axis=0)

    # Upsample estimated median layer back to original page dimensions
    wm_im = Image.fromarray(np.clip(wm_small, 0, 255).astype(np.uint8))
    wm_layer = np.array(wm_im.resize((w, h), resample=Image.Resampling.BILINEAR), dtype=np.float32)
    return wm_layer


def calculate_residual_correlation(
    image: Image.Image | np.ndarray,
    wm_layer: np.ndarray,
    mask: np.ndarray | None = None,
) -> float:
    """Calculate Pearson correlation coefficient between image background and estimated watermark pattern."""
    img_gray = image.convert("L") if isinstance(image, Image.Image) else Image.fromarray(image).convert("L")
    w, h = wm_layer.shape[1], wm_layer.shape[0]
    if img_gray.size != (w, h):
        img_gray = img_gray.resize((w, h), resample=Image.Resampling.BILINEAR)

    arr = np.array(img_gray, dtype=np.float64)
    # Watermark pattern: inversion of the watermark layer (darker = higher pattern strength)
    wm_pattern = 255.0 - wm_layer.astype(np.float64)

    # Exclude foreground text and anti-aliasing fringes to measure true background watermark residual
    eval_mask = mask if mask is not None else (arr > 150)
    if np.sum(eval_mask) < 100:
        return 0.0

    x = arr[eval_mask]
    y = wm_pattern[eval_mask]

    std_wm = float(np.std(y))
    std_arr = float(np.std(x))

    if std_wm < 1e-4 or std_arr < 1e-4:
        return 0.0

    mean_wm = np.mean(y)
    mean_arr = np.mean(x)

    covariance = np.mean((x - mean_arr) * (y - mean_wm))
    corr = covariance / (std_wm * std_arr)

    return float(abs(corr))


def remove_baked_watermark(
    pages: list[Image.Image],
    wm_layer: np.ndarray | None = None,
    check_alignment: bool = False,
) -> tuple[list[Image.Image], list[Issue]]:
    """Remove baked-in watermark via cross-page flat-field median division.

    Returns:
        tuple of (cleaned_pages, issues)
    """
    issues: list[Issue] = []
    if not pages:
        return [], issues

    if wm_layer is None:
        wm_layer = estimate_watermark_median(pages)

    if wm_layer is None:
        return list(pages), issues

    w, h = wm_layer.shape[1], wm_layer.shape[0]

    # Check for moving watermark if requested
    if check_alignment and len(pages) >= 3:
        # Check if watermark pattern moves across pages by comparing individual page difference
        diffs = []
        for p in pages:
            gray = p.convert("L")
            if gray.size != (w, h):
                gray = gray.resize((w, h), resample=Image.Resampling.BILINEAR)
            arr = np.array(gray, dtype=np.float32)
            # Find center of dark mass
            dark_pixels = arr < 220
            if np.sum(dark_pixels) > 0:
                cy, cx = np.mean(np.where(dark_pixels), axis=1)
                diffs.append((cy, cx))
        if len(diffs) >= 2:
            max_shift = max(
                abs(diffs[i][0] - diffs[0][0]) + abs(diffs[i][1] - diffs[0][1])
                for i in range(1, len(diffs))
            )
            if max_shift > 30.0:
                issues.append(
                    Issue(
                        id="moving_watermark_warning",
                        stage="s2_clean",
                        rule="watermark_removal",
                        severity=IssueSeverity.WARNING,
                        message="Variable or moving watermark detected: falling back to conservative cleaning.",
                    )
                )

    # If watermark layer is uniformly white, no watermark present
    if np.mean(wm_layer) >= 252.0 and np.min(wm_layer) >= 240.0:
        return list(pages), issues

    cleaned_pages: list[Image.Image] = []
    norm_wm = np.maximum(wm_layer / 255.0, 0.20)

    for p in pages:
        gray = p.convert("L")
        if gray.size != (w, h):
            gray = gray.resize((w, h), resample=Image.Resampling.BILINEAR)
        arr = np.array(gray, dtype=np.float32)
        # Flat field divide by watermark layer
        divided = np.clip(arr / norm_wm, 0, 255).astype(np.uint8)
        cleaned_pages.append(Image.fromarray(divided))

    return cleaned_pages, issues
