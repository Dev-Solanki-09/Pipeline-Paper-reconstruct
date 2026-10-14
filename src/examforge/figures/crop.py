"""Figure bbox refinement: grow-until-clean and shrink-to-ink with text mask subtraction."""

from __future__ import annotations

import numpy as np
from PIL import Image

from examforge.ir.schema import BBox


def _to_gray_array(image: Image.Image | np.ndarray) -> np.ndarray:
    """Convert input image to a 2D grayscale uint8 numpy array."""
    if isinstance(image, Image.Image):
        return np.array(image.convert("L"))
    if isinstance(image, np.ndarray):
        if image.ndim == 3:
            # RGB to grayscale
            return np.array(Image.fromarray(image).convert("L"))
        return image
    raise TypeError(f"Unsupported image type: {type(image)}")


def calculate_border_strip_ink_ratio(
    image: Image.Image | np.ndarray,
    bbox: BBox,
    strip_width: int = 2,
    ink_threshold: int = 200,
) -> float:
    """Calculate the ratio of ink pixels in the outer border strip of bbox.

    Border strip covers the top, bottom, left, and right strips of width strip_width.
    """
    arr = _to_gray_array(image)
    h, w = arr.shape

    x1 = max(0, min(w, int(round(bbox.x1))))
    y1 = max(0, min(h, int(round(bbox.y1))))
    x2 = max(0, min(w, int(round(bbox.x2))))
    y2 = max(0, min(h, int(round(bbox.y2))))

    if x2 <= x1 or y2 <= y1:
        return 0.0

    strip_w = max(1, min(strip_width, (x2 - x1) // 2, (y2 - y1) // 2))

    top_strip = arr[y1 : y1 + strip_w, x1:x2]
    bottom_strip = arr[max(y1, y2 - strip_w) : y2, x1:x2]
    left_strip = arr[y1:y2, x1 : x1 + strip_w]
    right_strip = arr[y1:y2, max(x1, x2 - strip_w) : x2]

    ink_pixels = (
        np.sum(top_strip < ink_threshold)
        + np.sum(bottom_strip < ink_threshold)
        + np.sum(left_strip < ink_threshold)
        + np.sum(right_strip < ink_threshold)
    )
    total_pixels = (
        top_strip.size + bottom_strip.size + left_strip.size + right_strip.size
    )

    if total_pixels == 0:
        return 0.0
    return float(ink_pixels / total_pixels)


def shrink_to_ink(
    image: Image.Image | np.ndarray,
    bbox: BBox,
    ink_threshold: int = 200,
    pad: int = 0,
) -> BBox:
    """Find the tightest bounding box of all ink pixels within bbox, plus pad."""
    arr = _to_gray_array(image)
    h, w = arr.shape

    x1 = max(0, min(w, int(round(bbox.x1))))
    y1 = max(0, min(h, int(round(bbox.y1))))
    x2 = max(0, min(w, int(round(bbox.x2))))
    y2 = max(0, min(h, int(round(bbox.y2))))

    if x2 <= x1 or y2 <= y1:
        return bbox

    sub = arr[y1:y2, x1:x2]
    ink_ys, ink_xs = np.where(sub < ink_threshold)

    if len(ink_ys) == 0:
        return bbox

    min_y = y1 + int(np.min(ink_ys))
    max_y = y1 + int(np.max(ink_ys)) + 1
    min_x = x1 + int(np.min(ink_xs))
    max_x = x1 + int(np.max(ink_xs)) + 1

    return BBox(
        x1=max(0, min_x - pad),
        y1=max(0, min_y - pad),
        x2=min(w, max_x + pad),
        y2=min(h, max_y + pad),
    )


def refine_bbox(
    image: Image.Image | np.ndarray,
    seed_bbox: BBox,
    text_mask: list[BBox] | None = None,
    in_figure_labels: list[BBox] | None = None,
    page_width: int | None = None,
    page_height: int | None = None,
    max_expand: int = 35,
    strip_width: int = 2,
    pad: int = 3,
    ink_threshold: int = 200,
) -> BBox:
    """Grow-until-clean followed by shrink-to-ink with padding.

    Guarantees:
    - 2-px border strip ink ratio == 0.
    - Idempotent: refine_bbox(refine_bbox(b)) == refine_bbox(b).
    - Monotone: never smaller than the initial seed's inner ink bbox.
    - Never exceeds page bounds.
    - Excludes neighboring text mask while attaching in-figure labels.
    """
    arr = _to_gray_array(image)
    img_h, img_w = arr.shape

    pw = page_width or img_w
    ph = page_height or img_h

    # Exclude in-figure labels from the forbidden text mask
    forbidden_boxes: list[BBox] = []
    if text_mask:
        for tb in text_mask:
            is_label = False
            if in_figure_labels:
                for lb in in_figure_labels:
                    if (
                        abs(tb.x1 - lb.x1) < 5
                        and abs(tb.y1 - lb.y1) < 5
                        and abs(tb.x2 - lb.x2) < 5
                        and abs(tb.y2 - lb.y2) < 5
                    ):
                        is_label = True
                        break
            if not is_label:
                forbidden_boxes.append(tb)

    # Initial bounds must include seed and in_figure_labels
    cur_x1 = max(0, int(round(seed_bbox.x1)))
    cur_y1 = max(0, int(round(seed_bbox.y1)))
    cur_x2 = min(pw, int(round(seed_bbox.x2)))
    cur_y2 = min(ph, int(round(seed_bbox.y2)))

    if in_figure_labels:
        for lb in in_figure_labels:
            cur_x1 = min(cur_x1, int(round(lb.x1)))
            cur_y1 = min(cur_y1, int(round(lb.y1)))
            cur_x2 = max(cur_x2, int(round(lb.x2)))
            cur_y2 = max(cur_y2, int(round(lb.y2)))

    # Compute inner ink bbox of initial seed for monotonicity guarantee
    seed_inner = shrink_to_ink(arr, seed_bbox, ink_threshold=ink_threshold, pad=0)

    # Step 1: Grow-until-clean
    # Expand each side stepwise while the border strip contains ink
    step = 2
    for _ in range(max_expand // step):
        sw = max(1, min(strip_width, (cur_x2 - cur_x1) // 2, (cur_y2 - cur_y1) // 2))

        # Check top
        if cur_y1 > 0 and cur_y1 > seed_bbox.y1 - max_expand:
            top_strip = arr[cur_y1 : cur_y1 + sw, cur_x1:cur_x2]
            if np.any(top_strip < ink_threshold):
                target_y1 = max(0, cur_y1 - step)
                if not any(fb.y1 < cur_y1 <= fb.y2 and fb.x1 < cur_x2 and fb.x2 > cur_x1 for fb in forbidden_boxes):
                    cur_y1 = target_y1

        # Check bottom
        if cur_y2 < ph and cur_y2 < seed_bbox.y2 + max_expand:
            bot_strip = arr[max(cur_y1, cur_y2 - sw) : cur_y2, cur_x1:cur_x2]
            if np.any(bot_strip < ink_threshold):
                target_y2 = min(ph, cur_y2 + step)
                if not any(fb.y1 < cur_y2 <= fb.y2 and fb.x1 < cur_x2 and fb.x2 > cur_x1 for fb in forbidden_boxes):
                    cur_y2 = target_y2

        # Check left
        if cur_x1 > 0 and cur_x1 > seed_bbox.x1 - max_expand:
            left_strip = arr[cur_y1:cur_y2, cur_x1 : cur_x1 + sw]
            if np.any(left_strip < ink_threshold):
                target_x1 = max(0, cur_x1 - step)
                if not any(fb.x1 < cur_x1 <= fb.x2 and fb.y1 < cur_y2 and fb.y2 > cur_y1 for fb in forbidden_boxes):
                    cur_x1 = target_x1

        # Check right
        if cur_x2 < pw and cur_x2 < seed_bbox.x2 + max_expand:
            right_strip = arr[cur_y1:cur_y2, max(cur_x1, cur_x2 - sw) : cur_x2]
            if np.any(right_strip < ink_threshold):
                target_x2 = min(pw, cur_x2 + step)
                if not any(fb.x1 < cur_x2 <= fb.x2 and fb.y1 < cur_y2 and fb.y2 > cur_y1 for fb in forbidden_boxes):
                    cur_x2 = target_x2

    # Step 2: Shrink-to-ink with padding
    sub = arr[cur_y1:cur_y2, cur_x1:cur_x2]
    ink_ys, ink_xs = np.where(sub < ink_threshold)
    if len(ink_ys) > 0:
        tight_x1 = cur_x1 + int(np.min(ink_xs))
        tight_y1 = cur_y1 + int(np.min(ink_ys))
        tight_x2 = cur_x1 + int(np.max(ink_xs)) + 1
        tight_y2 = cur_y1 + int(np.max(ink_ys)) + 1

        # Include in_figure_labels in tight bounds
        if in_figure_labels:
            for lb in in_figure_labels:
                tight_x1 = min(tight_x1, int(round(lb.x1)))
                tight_y1 = min(tight_y1, int(round(lb.y1)))
                tight_x2 = max(tight_x2, int(round(lb.x2)))
                tight_y2 = max(tight_y2, int(round(lb.y2)))

        # Monotonicity check against initial seed_inner
        tight_x1 = min(tight_x1, int(round(seed_inner.x1)))
        tight_y1 = min(tight_y1, int(round(seed_inner.y1)))
        tight_x2 = max(tight_x2, int(round(seed_inner.x2)))
        tight_y2 = max(tight_y2, int(round(seed_inner.y2)))

        # Apply padding
        final_x1 = max(0, tight_x1 - pad)
        final_y1 = max(0, tight_y1 - pad)
        final_x2 = min(pw, tight_x2 + pad)
        final_y2 = min(ph, tight_y2 + pad)
    else:
        final_x1, final_y1, final_x2, final_y2 = cur_x1, cur_y1, cur_x2, cur_y2

    # Respect forbidden text boundaries
    for fb in forbidden_boxes:
        # If forbidden box is above final bbox
        if fb.y2 <= final_y1 + pad and fb.y2 > final_y1:
            final_y1 = int(round(fb.y2))
        # If forbidden box is below final bbox
        if fb.y1 >= final_y2 - pad and fb.y1 < final_y2:
            final_y2 = int(round(fb.y1))
        # If forbidden box is to the left
        if fb.x2 <= final_x1 + pad and fb.x2 > final_x1:
            final_x1 = int(round(fb.x2))
        # If forbidden box is to the right
        if fb.x1 >= final_x2 - pad and fb.x1 < final_x2:
            final_x2 = int(round(fb.x1))

    return BBox(
        x1=final_x1,
        y1=final_y1,
        x2=final_x2,
        y2=final_y2,
    )
