"""
S3 Parse: Extract text blocks from pages.

For digital PDFs (which is what most coaching-institute PDFs are),
we use PyMuPDF's structured text extraction directly -- no OCR needed.
For scanned PDFs, this stage would call PaddleOCR/Tesseract; in M1,
we only handle digital text layers.

This stage:
1. Opens the PDF and iterates over pages that have valid text layers.
2. Calls page.get_text("dict") to get structured blocks with spans.
3. Converts each text block to an IR Block with bbox, language, and
   provenance (engine="pymupdf_text_layer").
4. Detects block language using a simple Devanagari character ratio.
5. Computes normalized bounding boxes for downstream furniture detection.
6. Skips pages without valid text layers (OCR deferred to later phase).

Design decisions:
- We use get_text("dict") rather than "text" because it gives us block-level
  bounding boxes and per-span font info, both needed for later stages.
- Language detection is character-ratio based: >30% Devanagari → Hindi.
- Confidence is 1.0 for digital text layers (perfect extraction).
- Block IDs are globally unique: "b{page}_{index}" format.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

import pymupdf

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    EngineSource,
    Issue,
    IssueSeverity,
    Lang,
    PageClassification,
)
from examforge.engines.paddle_vl import PaddleVLAdapter, PaddleVLConfig
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Threshold: if >30% of letter characters are Devanagari, classify as Hindi
DEVANAGARI_THRESHOLD = 0.30

# Minimum text length to consider a block (filters tiny artifacts)
MIN_BLOCK_TEXT_LENGTH = 2

# Devanagari Unicode range
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LETTER_RE = re.compile(r"\w", re.UNICODE)


class S3Parse(Stage):
    """
    Stage 3: Extract text blocks from the PDF text layer.

    Converts PyMuPDF's structured text output into IR Block objects
    with bounding boxes, language tags, and engine provenance.
    """

    name = "s3_parse"

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S3 requires pages to be populated by S0."""
        violations = []
        if not ctx.document.pages:
            violations.append("No pages found — S0 Intake must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        source = Path(ctx.document.source_path)
        issues: list[Issue] = []
        metrics: dict = {}

        doc = pymupdf.open(str(source))
        all_blocks: list[Block] = []
        block_counter = 0
        pages_processed = 0
        pages_skipped = 0

        for page_info in ctx.document.pages:
            page_num = page_info.page_number
            page_idx = page_num - 1  # 0-indexed for PyMuPDF

            if page_idx >= len(doc):
                issues.append(Issue(
                    id=f"s3_page_out_of_range_{page_num}",
                    stage=self.name,
                    page=page_num,
                    severity=IssueSeverity.WARNING,
                    message=f"Page {page_num} is out of range (PDF has {len(doc)} pages).",
                ))
                continue

            # Skip pages without valid text layer
            if not (page_info.has_text_layer and page_info.text_layer_valid):
                pages_skipped += 1
                if page_info.classification == PageClassification.QUESTIONS:
                    issues.append(Issue(
                        id=f"s3_no_text_layer_p{page_num}",
                        stage=self.name,
                        page=page_num,
                        severity=IssueSeverity.INFO,
                        message=(
                            f"Page {page_num} (classified as questions) has no "
                            f"valid text layer — skipping text extraction."
                        ),
                    ))
                continue

            page = doc[page_idx]
            page_blocks, block_counter = _extract_blocks_from_page(
                page, page_num, block_counter, page_info.width_px, page_info.height_px,
            )
            all_blocks.extend(page_blocks)
            pages_processed += 1

            logger.debug(
                "  Page %d: extracted %d blocks",
                page_num, len(page_blocks),
            )

        doc.close()

        # Merge into document (append to any existing blocks, don't replace)
        ctx.document.blocks.extend(all_blocks)

        # Metrics
        lang_counts = {"en": 0, "hi": 0, "mixed": 0, "unknown": 0}
        for b in all_blocks:
            lang_counts[b.lang.value] = lang_counts.get(b.lang.value, 0) + 1

        metrics.update({
            "total_blocks": len(all_blocks),
            "pages_processed": pages_processed,
            "pages_skipped": pages_skipped,
            "blocks_en": lang_counts.get("en", 0),
            "blocks_hi": lang_counts.get("hi", 0),
            "blocks_mixed": lang_counts.get("mixed", 0),
        })

        logger.info(
            "  Parse complete: %d blocks from %d pages (%d EN, %d HI)",
            len(all_blocks), pages_processed,
            lang_counts.get("en", 0), lang_counts.get("hi", 0),
        )

        return StageResult(
            document=ctx.document,
            metrics=metrics,
            issues=issues,
        )

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Check that blocks were extracted if there are question pages with text."""
        violations = []
        doc = result.document

        # Count question pages with valid text layers
        question_text_pages = sum(
            1
            for p in doc.pages
            if p.classification == PageClassification.QUESTIONS
            and p.has_text_layer
            and p.text_layer_valid
        )

        if question_text_pages > 0 and not doc.blocks:
            violations.append(
                f"No blocks extracted despite {question_text_pages} "
                f"question pages with valid text layers."
            )

        return violations


def _extract_blocks_from_page(
    page: pymupdf.Page,
    page_num: int,
    block_counter: int,
    page_width_px: int,
    page_height_px: int,
) -> tuple[list[Block], int]:
    """Extract Block objects from a single PDF page.

    Uses PyMuPDF's get_text("dict") for structured block+span data,
    giving us bounding boxes and font information per block.

    Args:
        page: PyMuPDF page object.
        page_num: 1-indexed page number.
        block_counter: Running counter for unique block IDs.
        page_width_px: Page width from PageInfo (for bbox normalization).
        page_height_px: Page height from PageInfo (for bbox normalization).

    Returns:
        (list of Blocks, updated block_counter)
    """
    blocks: list[Block] = []

    # Get structured text data
    text_dict = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

    for raw_block in text_dict.get("blocks", []):
        # Skip image blocks (type=1), we only want text (type=0)
        if raw_block.get("type", 0) != 0:
            continue

        # Assemble text from all spans in all lines
        text_parts = []
        for line in raw_block.get("lines", []):
            line_text_parts = []
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                if span_text:
                    line_text_parts.append(span_text)
            if line_text_parts:
                text_parts.append("".join(line_text_parts))
        text = "\n".join(text_parts).strip()

        # Skip empty or tiny blocks
        if len(text) < MIN_BLOCK_TEXT_LENGTH:
            continue

        # Bounding box (PyMuPDF gives float coords)
        bbox_raw = raw_block.get("bbox", (0, 0, 0, 0))
        bbox = BBox(
            x1=int(round(bbox_raw[0])),
            y1=int(round(bbox_raw[1])),
            x2=int(round(bbox_raw[2])),
            y2=int(round(bbox_raw[3])),
        )

        # Skip degenerate boxes
        if bbox.width <= 0 or bbox.height <= 0:
            continue

        # Normalized bbox (0-1 range, for furniture detection)
        bbox_norm = None
        if page_width_px > 0 and page_height_px > 0:
            bbox_norm = (
                round(bbox.x1 / page_width_px, 4),
                round(bbox.y1 / page_height_px, 4),
                round(bbox.x2 / page_width_px, 4),
                round(bbox.y2 / page_height_px, 4),
            )

        # Detect language
        lang = _detect_block_language(text)

        # Create the block
        block_id = f"b{page_num}_{block_counter}"
        block_counter += 1

        block = Block(
            id=block_id,
            page=page_num,
            type=BlockType.TEXT,
            bbox=bbox,
            bbox_norm=bbox_norm,
            order=len(blocks),  # Sequential within the page
            lang=lang,
            text=text,
            confidence=1.0,  # Digital text layer = perfect
            sources=[
                EngineSource(
                    engine="pymupdf_text_layer",
                    text=text,
                    confidence=1.0,
                ),
            ],
            status=BlockStatus.TRUSTED,
        )
        blocks.append(block)

    return blocks, block_counter


def _detect_block_language(text: str) -> Lang:
    """Detect language of a text block.

    Uses a character-ratio heuristic:
    - If >30% of letter characters are in the Devanagari Unicode range
      (U+0900-U+097F), classify as Hindi.
    - Otherwise classify as English.

    Args:
        text: The text to classify.

    Returns:
        Lang.HI if predominantly Devanagari, Lang.EN otherwise.
    """
    if not text:
        return Lang.UNKNOWN

    letters = _LETTER_RE.findall(text)
    if not letters:
        return Lang.UNKNOWN

    devanagari_count = len(_DEVANAGARI_RE.findall(text))
    total_letters = len(letters)

    if total_letters == 0:
        return Lang.UNKNOWN

    ratio = devanagari_count / total_letters

    if ratio > DEVANAGARI_THRESHOLD:
        return Lang.HI
    return Lang.EN
