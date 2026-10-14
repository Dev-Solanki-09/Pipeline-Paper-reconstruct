"""Vector ruling extraction from drawings for table structure reconstruction."""

from __future__ import annotations

from typing import Any
import pymupdf


def extract_rulings_from_drawings(
    drawings: list[dict[str, Any]],
    min_length: float = 20.0,
    tolerance: float = 2.5,
) -> tuple[list[tuple[float, float, float, float]], list[tuple[float, float, float, float]]]:
    """Extract horizontal and vertical rulings from vector drawings.

    Returns:
        tuple of (h_lines, v_lines), where each line is (x1, y1, x2, y2).
    """
    h_lines: list[tuple[float, float, float, float]] = []
    v_lines: list[tuple[float, float, float, float]] = []

    for d in drawings:
        rect = d.get("rect")
        if rect is None:
            continue

        w = rect.width
        h = rect.height

        # Thin rectangle representing a horizontal line
        if h <= tolerance and w >= min_length:
            h_lines.append((rect.x0, (rect.y0 + rect.y1) / 2.0, rect.x1, (rect.y0 + rect.y1) / 2.0))
        # Thin rectangle representing a vertical line
        elif w <= tolerance and h >= min_length:
            v_lines.append(((rect.x0 + rect.x1) / 2.0, rect.y0, (rect.x0 + rect.x1) / 2.0, rect.y1))

        # Check path items for line commands
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)
                if dy <= tolerance and dx >= min_length:
                    h_lines.append((min(p1.x, p2.x), (p1.y + p2.y) / 2.0, max(p1.x, p2.x), (p1.y + p2.y) / 2.0))
                elif dx <= tolerance and dy >= min_length:
                    v_lines.append(((p1.x + p2.x) / 2.0, min(p1.y, p2.y), (p1.x + p2.x) / 2.0, max(p1.y, p2.y)))

    return h_lines, v_lines
