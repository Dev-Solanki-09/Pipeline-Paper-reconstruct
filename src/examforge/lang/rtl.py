"""
RTL (Right-to-Left) script and language support.

Handles Urdu (ur), Arabic (ar), Persian (fa), and Hebrew (he) reading order,
direction attributes, and visual block ordering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from examforge.ir.schema import Block

RTL_LANGUAGES = {"ur", "ar", "fa", "he", "ps", "sd"}
RTL_SCRIPTS = {"Arab", "Hebr"}


def is_rtl_language(lang: str) -> bool:
    """Check if the given language code is Right-to-Left."""
    if not lang:
        return False
    return lang.lower().strip() in RTL_LANGUAGES


def format_dir_attribute(lang: str) -> str:
    """Return HTML dir attribute for the language."""
    return 'dir="rtl"' if is_rtl_language(lang) else 'dir="ltr"'


def reorder_rtl_blocks(blocks: list[Block]) -> list[Block]:
    """
    Reorder blocks for RTL visual reading order.

    Groups blocks into vertical bands (lines) and sorts blocks within each band
    from right to left (descending x coordinates).
    """
    if not blocks or len(blocks) <= 1:
        return list(blocks)

    # Sort primarily by y1
    sorted_by_y = sorted(blocks, key=lambda b: (b.page, b.bbox.y1))

    # Group into lines where vertical overlap is significant
    lines: list[list[Block]] = []
    current_line: list[Block] = [sorted_by_y[0]]

    for b in sorted_by_y[1:]:
        ref_b = current_line[-1]
        line_height = ref_b.bbox.height
        y_diff = abs(b.bbox.y1 - ref_b.bbox.y1)

        # Same line if y difference is small relative to height
        if b.page == ref_b.page and y_diff < max(5.0, line_height * 0.5):
            current_line.append(b)
        else:
            lines.append(current_line)
            current_line = [b]

    if current_line:
        lines.append(current_line)

    # Sort each line right-to-left (x2 descending)
    ordered_blocks: list[Block] = []
    for line in lines:
        line_sorted = sorted(line, key=lambda b: -b.bbox.x2)
        ordered_blocks.extend(line_sorted)

    return ordered_blocks
