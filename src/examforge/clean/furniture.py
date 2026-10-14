"""Furniture and script-aware page number detection with content preservation guards."""

from __future__ import annotations

import re
from examforge.ir.schema import Block

# Question/option number patterns that must never be dropped as furniture
_QUESTION_START_RE = re.compile(
    r"^\s*(?:Q\.?\s*)?(?:\d+|[०-९]+)\s*[.):]",
    re.IGNORECASE,
)
_OPTION_START_RE = re.compile(
    r"^\s*\(([A-Da-d1-4]|[०-९]+)\)",
)
_SUBPART_START_RE = re.compile(
    r"^\s*(?:\([a-zA-Z0-9ivxlcdm]+\)|[a-zA-Z0-9ivxlcdm]+[.)])\s*",
    re.IGNORECASE,
)

# Script-aware page number regexes
_PAGE_NUM_ARABIC_RE = re.compile(
    r"^\s*(?:page\s*)?(\d+)(?:\s*(?:/|of)\s*\d+)?\s*$",
    re.IGNORECASE,
)
_PAGE_NUM_DEVANAGARI_RE = re.compile(
    r"^\s*(?:पृष्ठ\s*)?([०-९]+)(?:\s*/\s*[०-९]+)?\s*$",
)
_PAGE_NUM_ROMAN_RE = re.compile(
    r"^\s*(?:page\s*)?([ivxlcdm]+)\s*$",
    re.IGNORECASE,
)


def is_protected_content(text: str, max_length: int = 80) -> bool:
    """Return True if block contains question, option, or subpart content that must not be dropped."""
    cleaned = text.strip()
    if len(cleaned) > max_length:
        return True
    if _QUESTION_START_RE.match(cleaned):
        return True
    if _OPTION_START_RE.match(cleaned):
        return True
    if _SUBPART_START_RE.match(cleaned):
        return True
    return False


def find_repeating_furniture_blocks(
    blocks: list[Block],
    min_fraction: float = 0.5,
    tolerance: float = 0.03,
    max_furniture_length: int = 80,
) -> list[str]:
    """Identify blocks that repeat across >= min_fraction of pages at extreme top/bottom."""
    num_pages = len({b.page for b in blocks})
    if num_pages <= 1:
        return []

    min_page_count = max(2, int(num_pages * min_fraction))

    # Map normalized y position & cleaned text to block IDs
    clusters: list[tuple[float, str, list[str]]] = []

    for b in blocks:
        if not b.bbox_norm:
            continue
        raw_text = b.text.strip()
        if not raw_text or is_protected_content(raw_text, max_length=max_furniture_length):
            continue

        clean_text = raw_text.lower()
        norm_y = b.bbox_norm[1]

        # Match existing cluster within tolerance
        matched = False
        for i, (cy, ctext, ids) in enumerate(clusters):
            if ctext == clean_text and abs(norm_y - cy) <= tolerance:
                ids.append(b.id)
                matched = True
                break

        if not matched:
            clusters.append((norm_y, clean_text, [b.id]))

    furniture_ids: list[str] = []
    for y_pos, text, ids in clusters:
        # Require header area (<0.12) or footer area (>0.88)
        if (y_pos < 0.12 or y_pos > 0.88) and len(ids) >= min_page_count:
            furniture_ids.extend(ids)

    return furniture_ids


def detect_page_numbers_script_aware(blocks: list[Block]) -> list[str]:
    """Find blocks representing page numbers in Arabic, Devanagari, or Roman numerals."""
    page_num_ids: list[str] = []

    for b in blocks:
        text = b.text.strip()
        if not text:
            continue

        # Skip protected question/option content
        if is_protected_content(text, max_length=40):
            continue

        # Position guard: page numbers are in header (<0.15) or footer (>0.85)
        if b.bbox_norm and not (b.bbox_norm[1] < 0.15 or b.bbox_norm[1] > 0.85):
            continue

        if _PAGE_NUM_ARABIC_RE.match(text):
            page_num_ids.append(b.id)
        elif _PAGE_NUM_DEVANAGARI_RE.match(text):
            page_num_ids.append(b.id)
        elif _PAGE_NUM_ROMAN_RE.match(text):
            page_num_ids.append(b.id)

    return page_num_ids
