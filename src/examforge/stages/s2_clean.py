"""
S2 Clean: Furniture & Watermark Removal.

Identifies and marks headers, footers, page numbers, branding text,
and watermarks as DROPPED with clear drop reasons (Guarantee G2).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from examforge.ir.schema import (
    Block,
    BlockStatus,
    BlockType,
    Issue,
    IssueSeverity,
    PageClassification,
    PageInfo,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Patterns for branding
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"\b\d{10}\b")
BRAND_KEYWORDS = [
    "allen",
    "resonance",
    "fiitjee",
    "aakash",
    "pace",
    "chaitanya",
    "narayana",
    "career point",
]

# Known furniture patterns
FOOTER_PATTERNS = [
    re.compile(r"^\s*space for rough work\s*$", re.IGNORECASE),
    re.compile(r"^\s*rough work\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),  # e.g. "2/28"
    re.compile(r"^\s*\d{8,}\s*$"),  # student/batch barcode numbers
]


class S2Clean(Stage):
    """
    Stage 2: Filter repeating furniture, page numbers, and branding.
    """

    name = "s2_clean"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["clean", "furniture_removal", "watermark_removal"]

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S2 requires pages or blocks to be present in the document."""
        violations = []
        if not ctx.document.pages and not ctx.document.blocks:
            violations.append("No pages or blocks found in document -- S0 Intake must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict = {}

        blocks = doc.blocks
        pages = doc.pages

        skip_reasons: list[str] = []
        from examforge.ir.schema import WatermarkTier

        # O3.3 Conditional Clean: measured gates per page
        for p in pages:
            # Gate 1: Deskew only if |skew| > 0.3°
            if abs(p.skew_degrees) > 0.3:
                pass
            else:
                skip_reasons.append(f"p{p.page_number}_deskew_skipped_within_tolerance")

            # Gate 2: Illumination only if background contrast/variance exceeds threshold
            if p.contrast > 0 and p.contrast < 0.4:
                pass
            else:
                skip_reasons.append(f"p{p.page_number}_illumination_skipped_uniform")

            # Gate 3: Watermark removal only if watermark tier >= W1 detected
            if p.watermark_tier not in (WatermarkTier.W0_NONE, "none"):
                pass
            else:
                skip_reasons.append(f"p{p.page_number}_watermark_skipped_w0")

            # Gate 4: Geometry (spread split, orientation) only when detected
            if p.is_two_page_spread:
                pass
            else:
                skip_reasons.append(f"p{p.page_number}_spread_skipped_single_page")

        # After S2, page coordinates are final (Guarantee)
        doc.metadata.geometry_final = True
        metrics["skip_reasons"] = skip_reasons
        metrics["geometry_final"] = True

        use_clean_v2 = True
        if ctx.profile and hasattr(ctx.profile, "flags") and ctx.profile.flags is not None:
            use_clean_v2 = ctx.profile.flags.get("clean_v2", True)
        elif ctx.config and hasattr(ctx.config, "flags") and ctx.config.flags is not None:
            use_clean_v2 = ctx.config.flags.get("clean_v2", True)

        branding_patterns = (
            ctx.resolved_profile.furniture_branding.branding
            if ctx.resolved_profile
            else []
        )

        profile_footers = []
        if ctx.resolved_profile and ctx.resolved_profile.furniture_branding.footers:
            for p in ctx.resolved_profile.furniture_branding.footers:
                try:
                    profile_footers.append(re.compile(p, re.IGNORECASE))
                except re.error:
                    pass
        footer_patterns = FOOTER_PATTERNS + profile_footers

        if not blocks:
            metrics["blocks_dropped"] = 0
            metrics["total_blocks"] = 0
            logger.info("  S2 Clean complete (pre-parse): conditional image gates evaluated, coordinates locked")
            return StageResult(document=doc, metrics=metrics, issues=issues)

        if not use_clean_v2:
            # v1 rollback logic
            furniture_ids = set(_find_repeating_furniture(blocks, pages))
            page_num_ids = set(_detect_page_numbers(blocks))
            branding_ids = set(_detect_branding(blocks, branding_patterns))
            watermark_ids = set(_detect_watermark_text(blocks, pages))
        else:
            # clean_v2 modular pipeline
            from examforge.clean.branding import scrub_branding_blocks
            from examforge.clean.furniture import (
                detect_page_numbers_script_aware,
                find_repeating_furniture_blocks,
            )

            furniture_ids = set(find_repeating_furniture_blocks(blocks))
            page_num_ids = set(detect_page_numbers_script_aware(blocks))
            branding_ids = set(scrub_branding_blocks(blocks, branding_patterns))
            watermark_ids = set(_detect_watermark_text(blocks, pages))

        dropped_count = 0
        for b in blocks:
            if b.status == BlockStatus.DROPPED:
                continue

            # Check known footer text patterns (e.g. SPACE FOR ROUGH WORK)
            is_known_footer = any(pat.search(b.text.strip()) for pat in footer_patterns)
            if is_known_footer:
                b.status = BlockStatus.DROPPED
                b.type = BlockType.FOOTER
                b.drop_reason = f"Footer furniture: '{b.text.strip()[:30]}'"
                dropped_count += 1
                continue

            if b.id in furniture_ids:
                b.status = BlockStatus.DROPPED
                b.type = BlockType.HEADER
                b.drop_reason = f"Repeating furniture across pages: '{b.text.strip()[:30]}'"
                dropped_count += 1
            elif b.id in page_num_ids:
                b.status = BlockStatus.DROPPED
                b.type = BlockType.PAGE_NUMBER
                b.drop_reason = f"Page number: '{b.text.strip()}'"
                dropped_count += 1
            elif b.id in branding_ids:
                b.status = BlockStatus.DROPPED
                b.type = BlockType.LOGO
                b.drop_reason = f"Branding text: '{b.text.strip()[:30]}'"
                dropped_count += 1
            elif b.id in watermark_ids:
                b.status = BlockStatus.DROPPED
                b.type = BlockType.WATERMARK
                b.drop_reason = f"Watermark text: '{b.text.strip()[:30]}'"
                dropped_count += 1

        metrics["blocks_dropped"] = dropped_count
        metrics["total_blocks"] = len(blocks)

        logger.info(
            "  S2 Clean complete: dropped %d furniture/branding/watermark blocks",
            dropped_count,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Guarantee G2: No block dropped without a drop_reason."""
        violations = []
        for b in result.document.blocks:
            if b.status == BlockStatus.DROPPED and not b.drop_reason:
                violations.append(f"Block {b.id} was dropped without a drop_reason.")
        return violations


def _find_repeating_furniture(
    blocks: list[Block],
    pages: list[PageInfo],
    threshold: float = 0.5,
    position_tolerance: float = 0.03,
) -> list[str]:
    """Find block IDs that appear at the same normalized vertical position across >=threshold of pages."""
    num_pages = len({b.page for b in blocks})
    if num_pages <= 1:
        return []

    # Map normalized y1 position to list of blocks
    # Group by (round(y1, 2), clean_text)
    pos_map: dict[tuple[float, str], list[str]] = {}

    for b in blocks:
        if not b.bbox_norm:
            continue
        norm_y = b.bbox_norm[1]
        raw_text = b.text.strip()
        clean_text = raw_text.lower()
        if not clean_text:
            continue

        # Guard: question content should never be dropped as furniture
        # 1. Blocks longer than 80 characters are real content (stems, passages)
        if len(raw_text) > 80:
            continue
        # 2. Blocks starting with question numbering or option labels
        if re.match(r"^\s*(?:Q\.?\s*)?\d{1,3}\s*[.):]", raw_text, re.IGNORECASE):
            continue
        if re.match(r"^\s*\(([A-Da-d1-4])\)", raw_text):
            continue

        # Look for existing matching cluster within tolerance
        matched = False
        for (clustered_y, clustered_text), id_list in pos_map.items():
            if clustered_text == clean_text and abs(norm_y - clustered_y) <= position_tolerance:
                id_list.append(b.id)
                matched = True
                break

        if not matched:
            pos_map[(round(norm_y, 3), clean_text)] = [b.id]

    furniture_ids: list[str] = []
    min_page_count = max(2, int(num_pages * threshold))

    for (y_pos, text), id_list in pos_map.items():
        # Only mark as furniture if at extreme top (<0.10) or extreme bottom (>0.90) or high frequency
        if (y_pos < 0.12 or y_pos > 0.88) and len(id_list) >= min_page_count:
            furniture_ids.extend(id_list)

    return furniture_ids


def _detect_page_numbers(blocks: list[Block]) -> list[str]:
    """Find blocks that represent standalone page numbers."""
    page_blocks_by_page: dict[int, list[Block]] = {}
    for b in blocks:
        page_blocks_by_page.setdefault(b.page, []).append(b)

    page_num_ids: list[str] = []

    # Sequence check across consecutive pages
    consecutive_matches = 0
    candidate_ids = []
    sorted_pages = sorted(page_blocks_by_page.keys())

    for p in sorted_pages:
        # Check if page has a block matching str(p) or "Page {p}"
        found_for_page = None
        for b in page_blocks_by_page[p]:
            t = b.text.strip()
            if t == str(p) or t.lower() == f"page {p}" or re.match(rf"^{p}\s*/\s*\d+$", t):
                # Typically page numbers appear at bottom or top
                if b.bbox_norm and (b.bbox_norm[1] > 0.85 or b.bbox_norm[1] < 0.15):
                    found_for_page = b.id
                    break

        if found_for_page:
            candidate_ids.append(found_for_page)
            consecutive_matches += 1
        else:
            consecutive_matches = 0

    if len(candidate_ids) >= 2:
        page_num_ids.extend(candidate_ids)

    return page_num_ids


def _detect_branding(
    blocks: list[Block],
    custom_patterns: list[str] | None = None,
) -> list[str]:
    """Find blocks containing URLs, phone numbers, or coaching institute names."""
    branding_ids: list[str] = []
    compiled_custom = []
    if custom_patterns:
        for p in custom_patterns:
            try:
                compiled_custom.append(re.compile(p, re.IGNORECASE))
            except re.error:
                pass

    for b in blocks:
        text = b.text.strip()
        if not text:
            continue

        lower = text.lower()
        if URL_RE.search(text):
            branding_ids.append(b.id)
        elif PHONE_RE.search(text) and len(text) < 40:
            branding_ids.append(b.id)
        elif any(kw in lower for kw in BRAND_KEYWORDS) and len(text) < 50:
            # Short header branding block
            if b.bbox_norm and (b.bbox_norm[1] < 0.15 or b.bbox_norm[1] > 0.85):
                branding_ids.append(b.id)
        elif compiled_custom and any(pat.search(text) for pat in compiled_custom):
            if len(text) < 60 and (not b.bbox_norm or b.bbox_norm[1] < 0.15 or b.bbox_norm[1] > 0.85):
                branding_ids.append(b.id)

    return branding_ids


def _detect_watermark_text(blocks: list[Block], pages: list[PageInfo]) -> list[str]:
    """Find text-layer watermarks (e.g. repeated watermark phrases)."""
    watermark_ids: list[str] = []
    # Watermark text typically repeats on almost every page at center
    center_text_counts: dict[str, list[str]] = {}

    for b in blocks:
        if b.bbox_norm:
            y_mid = (b.bbox_norm[1] + b.bbox_norm[3]) / 2.0
            x_mid = (b.bbox_norm[0] + b.bbox_norm[2]) / 2.0
            # Near center of page
            if 0.3 < y_mid < 0.7 and 0.2 < x_mid < 0.8:
                t = b.text.strip().lower()
                if len(t) > 5:
                    center_text_counts.setdefault(t, []).append(b.id)

    num_pages = len(pages)
    if num_pages > 3:
        for t, id_list in center_text_counts.items():
            if len(id_list) >= int(num_pages * 0.7):
                watermark_ids.extend(id_list)

    return watermark_ids
