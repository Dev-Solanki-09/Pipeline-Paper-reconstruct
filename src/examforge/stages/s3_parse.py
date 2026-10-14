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
    PageProcessingPath,
)
from examforge.engines.paddle_vl import PaddleVLAdapter, PaddleVLConfig
from examforge.ocr.glyph_cache import GlyphDecoder
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Threshold: if >30% of letter characters are Devanagari, classify as Hindi
DEVANAGARI_THRESHOLD = 0.30

# Minimum text length to consider a block (filters tiny artifacts)
MIN_BLOCK_TEXT_LENGTH = 2

# Devanagari Unicode range
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_LETTER_RE = re.compile(r"\w", re.UNICODE)

# Layout recognition regex patterns for layout-aware tagging
_HEADER_RE = re.compile(
    r"^(?:PART\s*[-–:]?\s*[0-9IVX]+|SECTION\s*[-–:]?\s*[A-Za-z0-9()]+|PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY|BOTANY|ZOOLOGY)\b",
    re.IGNORECASE,
)
_MATH_SYMBOLS_RE = re.compile(
    r"(?:\\(?:frac|sqrt|int|sum|prod|alpha|beta|gamma|theta|lambda|pi|sigma|omega|Delta|Omega)|[=<>≤≥±×÷√∫∑∏]|\^[0-9a-zA-Z{]|_{[0-9a-zA-Z]|(?:sin|cos|tan|log|ln)\s*\()"
)
_TABLE_RE = re.compile(
    r"(?:(?:Column|List|Table)\s*[-–:]?\s*[I|1|A])",
    re.IGNORECASE,
)

EARLY_EXIT_CLASSES = {
    PageClassification.COVER,
    PageClassification.INSTRUCTIONS,
    PageClassification.ROUGH_WORK,
    PageClassification.BLANK,
    PageClassification.OMR,
}


class S3Parse(Stage):
    """
    Stage 3: Extract text blocks from the PDF text layer or vision model (Phase O2).

    Digital-first architecture:
    - Path A: Direct structured PyMuPDF extraction with sub/superscript baseline analysis (0 model calls).
    - Path B: Scanned/raster pages escalated to PaddleOCR-VL-1.6.
    - Path C: Digital broken/legacy fonts decoded with GlyphDecoder font mapping.
    - Early exit: Non-question pages skipped automatically.
    """

    name = "s3_parse"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["paddle_vl", "pymupdf_text"]

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
        path_a_pages = 0
        path_b_pages = 0
        path_c_pages = 0
        early_exit_pages = 0
        glyph_decoder = GlyphDecoder()

        # Initialize Paddle-VL 1.6 adapter
        vl_config = None
        if ctx.config and hasattr(ctx.config, "engines"):
            engine_cfg = ctx.config.engines.get("paddlevl") or ctx.config.engines.get("paddleocr")
            if engine_cfg:
                vl_config = PaddleVLConfig(
                    model_name=engine_cfg.model_name or "PaddleOCR-VL-1.6",
                    pipeline_version=engine_cfg.pipeline_version or "v1.6",
                    api_url=engine_cfg.api_url,
                    api_key=engine_cfg.api_key,
                    timeout_s=engine_cfg.timeout_s,
                    use_gpu=engine_cfg.use_gpu,
                    max_retries=engine_cfg.max_retries,
                )
        vl_adapter = PaddleVLAdapter(config=vl_config)

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

            # O2.6 Per-page early exit: skip non-question pages
            if page_info.classification in EARLY_EXIT_CLASSES:
                early_exit_pages += 1
                pages_skipped += 1
                logger.debug(
                    "  Page %d: early exit for %s page",
                    page_num, page_info.classification.value,
                )
                continue

            # Determine execution path
            path = page_info.processing_path or PageProcessingPath.PATH_A

            # Resolve page image if available
            page_img_path = None
            if page_info.image_path and ctx.run_dir:
                candidate = ctx.run_dir / page_info.image_path
                if candidate.exists():
                    page_img_path = candidate

            page_blocks: list[Block] = []

            if path == PageProcessingPath.PATH_A:
                # O2.2 Path A (digital, valid text layer) -> ZERO model inference
                path_a_pages += 1
                if page_info.has_text_layer and page_info.text_layer_valid:
                    page = doc[page_idx]
                    page_blocks, block_counter = _extract_blocks_from_page(
                        page, page_num, block_counter, page_info.width_px, page_info.height_px,
                    )
            elif path == PageProcessingPath.PATH_C:
                # O2.4 Path C (broken/legacy fonts) -> glyph-level decoding
                path_c_pages += 1
                if page_info.has_text_layer:
                    page = doc[page_idx]
                    page_blocks, block_counter = _extract_blocks_from_page(
                        page, page_num, block_counter, page_info.width_px, page_info.height_px,
                        glyph_decoder=glyph_decoder,
                    )
                # If glyph decoding recovered no blocks, fallback to vl_adapter
                if not page_blocks:
                    page_blocks = vl_adapter.extract_page(
                        image_path=page_img_path,
                        page_num=page_num,
                        fallback_blocks=[],
                    )
            else:
                # O2.3 Path B (scanned / raster) -> Paddle-VL-1.6 inference
                path_b_pages += 1
                base_blocks = []
                if page_info.has_text_layer and page_info.text_layer_valid:
                    page = doc[page_idx]
                    base_blocks, block_counter = _extract_blocks_from_page(
                        page, page_num, block_counter, page_info.width_px, page_info.height_px,
                    )
                page_blocks = vl_adapter.extract_page(
                    image_path=page_img_path,
                    page_num=page_num,
                    fallback_blocks=base_blocks,
                )

            # O2.5 Second engine on demand: check low-confidence blocks
            for b in page_blocks:
                if b.confidence < 0.85 and path == PageProcessingPath.PATH_B:
                    issues.append(Issue(
                        id=f"s3_low_confidence_{b.id}",
                        stage=self.name,
                        page=page_num,
                        severity=IssueSeverity.WARNING,
                        message=f"Block {b.id} on page {page_num} has low confidence ({b.confidence:.2f}) on Path B.",
                    ))

            # Skip pages that yielded no text
            if not page_blocks:
                pages_skipped += 1
                if page_info.classification == PageClassification.QUESTIONS:
                    issues.append(Issue(
                        id=f"s3_no_text_layer_p{page_num}",
                        stage=self.name,
                        page=page_num,
                        severity=IssueSeverity.INFO,
                        message=(
                            f"Page {page_num} (classified as questions) yielded no "
                            f"blocks from text layer / Paddle-VL — skipping."
                        ),
                    ))
                continue

            all_blocks.extend(page_blocks)
            pages_processed += 1

            logger.debug(
                "  Page %d (%s): extracted %d blocks",
                page_num, path.value, len(page_blocks),
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
            "path_a_pages": path_a_pages,
            "path_b_pages": path_b_pages,
            "path_c_pages": path_c_pages,
            "early_exit_pages": early_exit_pages,
            "model_inferences": vl_adapter.get_inference_count(),
            "blocks_en": lang_counts.get("en", 0),
            "blocks_hi": lang_counts.get("hi", 0),
            "blocks_mixed": lang_counts.get("mixed", 0),
        })

        logger.info(
            "  Parse complete: %d blocks from %d pages (%d EN, %d HI, Path A=%d, Path B=%d, Path C=%d, EarlyExit=%d, Inferences=%d)",
            len(all_blocks), pages_processed,
            lang_counts.get("en", 0), lang_counts.get("hi", 0),
            path_a_pages, path_b_pages, path_c_pages, early_exit_pages,
            vl_adapter.get_inference_count(),
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

        # Count question pages with valid text layers (excluding early exit pages)
        question_text_pages = sum(
            1
            for p in doc.pages
            if p.classification == PageClassification.QUESTIONS
            and p.has_text_layer
            and p.text_layer_valid
            and p.classification not in EARLY_EXIT_CLASSES
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
    glyph_decoder: GlyphDecoder | None = None,
) -> tuple[list[Block], int]:
    """Extract Block objects from a single PDF page.

    Uses PyMuPDF's get_text("dict") for structured block+span data,
    giving us bounding boxes and font information per block.
    Supports:
    - Sub/superscript detection from baseline offsets and font-size ratios
    - GlyphDecoder decoding for broken/legacy fonts (Path C)
    - Block layout typing (Header, Formula, Table, Text)

    Args:
        page: PyMuPDF page object.
        page_num: 1-indexed page number.
        block_counter: Running counter for unique block IDs.
        page_width_px: Page width from PageInfo (for bbox normalization).
        page_height_px: Page height from PageInfo (for bbox normalization).
        glyph_decoder: Optional GlyphDecoder for Path C font transliteration.

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

        text_parts = []
        for line in raw_block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            # Dominant font size and baseline in this line
            sizes = [s.get("size", 10.0) for s in spans if s.get("text", "").strip()]
            dominant_size = max(set(sizes), key=sizes.count) if sizes else 10.0
            baselines = [
                s.get("origin", (0, 0))[1]
                for s in spans
                if "origin" in s and s.get("text", "").strip()
            ]
            dominant_baseline = max(set(baselines), key=baselines.count) if baselines else 0.0

            line_text_parts = []
            for span in spans:
                span_text = span.get("text", "")
                if not span_text:
                    continue

                font_name = span.get("font", "")
                if glyph_decoder:
                    span_text = glyph_decoder.decode_text(font_name, span_text)

                flags = span.get("flags", 0)
                size = span.get("size", dominant_size)
                origin = span.get("origin")
                y_base = origin[1] if origin else span.get("bbox", [0, 0, 0, 0])[3]

                clean_span = span_text.strip()
                if clean_span and dominant_size > 0:
                    # Subscript / superscript reconstruction
                    if flags & 1:  # PyMuPDF superscript flag
                        span_text = span_text.replace(clean_span, f"^{{{clean_span}}}")
                    elif size < dominant_size * 0.85:
                        if dominant_baseline and y_base < dominant_baseline - 1.5:
                            span_text = span_text.replace(clean_span, f"^{{{clean_span}}}")
                        elif dominant_baseline and y_base > dominant_baseline + 1.5:
                            span_text = span_text.replace(clean_span, f"_{{{clean_span}}}")

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

        # Layout classification
        stripped = text.strip()
        b_type = BlockType.TEXT
        latex = None
        if _HEADER_RE.search(stripped):
            b_type = BlockType.HEADER
        elif _TABLE_RE.search(stripped):
            b_type = BlockType.TABLE
        elif _MATH_SYMBOLS_RE.search(stripped):
            b_type = BlockType.FORMULA
            latex = stripped

        # Engine source and confidence
        engine_name = "glyph_decoder" if glyph_decoder else "pymupdf_text_layer"
        confidence = 0.95 if glyph_decoder else 1.0

        block_id = f"b{page_num}_{block_counter}"
        block_counter += 1

        block = Block(
            id=block_id,
            page=page_num,
            type=b_type,
            bbox=bbox,
            bbox_norm=bbox_norm,
            order=len(blocks),  # Sequential within the page
            lang=lang,
            text=text,
            latex=latex,
            confidence=confidence,
            sources=[
                EngineSource(
                    engine=engine_name,
                    text=text,
                    confidence=confidence,
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
