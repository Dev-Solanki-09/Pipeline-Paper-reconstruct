"""
S0 Intake: open the source document and extract per-page metadata.

This is the first stage in the pipeline. It:
1. Opens the PDF with PyMuPDF (fitz)
2. Extracts per-page metrics: dimensions, DPI estimate, text-layer presence
3. Detects legacy Hindi fonts (Kruti Dev, Chanakya, etc.) that produce gibberish
4. Classifies pages (cover, instructions, questions, blank, etc.)
5. Renders page images for downstream OCR and visual processing
6. Harvests exam metadata from cover/header pages (name, year, series)

Design decisions:
- PyMuPDF chosen for: speed, PDF text+image extraction, font info, rendering
- Page images rendered at 300 DPI (configurable) for OCR quality
- Legacy font detection: check font names against a known list + validate
  extracted text has enough Devanagari characters
- Page classification is heuristic in M1 (question pages have many short
  text blocks); will be refined with templates in M4
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

from examforge.ir.schema import (
    ExamDocument,
    ExamMetadata,
    Issue,
    IssueSeverity,
    PageClassification,
    PageInfo,
    PageProcessingPath,
    PageStatus,
    WatermarkTier,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Known legacy Hindi fonts that produce Latin gibberish instead of Unicode
LEGACY_HINDI_FONTS = {
    "kruti dev", "krutidev", "chanakya", "devlys", "dvttsurekh",
    "shusha", "shivaji", "walkman chanakya", "agra", "ananda",
    "kundli", "surekh", "mangal",  # Mangal is sometimes misused
}

# DPI to render page images for OCR
DEFAULT_RENDER_DPI = 300

# Minimum fraction of Devanagari characters for a valid Hindi text layer
MIN_DEVANAGARI_RATIO = 0.05


class S0Intake(Stage):
    """
    Stage 0: Intake and triage.

    Opens the source PDF, extracts page-level metadata, detects
    text layers and legacy fonts, classifies pages, and renders
    page images for downstream stages.
    """

    name = "s0_intake"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["intake", "render"]

    def run(self, ctx: StageContext) -> StageResult:
        source = Path(ctx.document.source_path)
        issues: list[Issue] = []
        metrics: dict = {}

        doc = fitz.open(str(source))
        total_pages = len(doc)
        metrics["total_pages"] = total_pages
        logger.info("  Opened %s: %d pages", source.name, total_pages)

        # Create pages subdirectory for rendered images
        pages_dir = ctx.stage_dir / "pages"
        pages_dir.mkdir(exist_ok=True)

        pages: list[PageInfo] = []
        metadata = ExamMetadata(source_type=_detect_source_type(doc))
        legacy_font_pages: list[int] = []

        limit_pages = total_pages
        if ctx.config and ctx.config.max_pages is not None:
            limit_pages = min(total_pages, ctx.config.max_pages)

        for page_idx in range(limit_pages):
            page_num = page_idx + 1  # 1-indexed
            page = doc[page_idx]

            # Basic dimensions
            rect = page.rect
            width_px = int(rect.width)
            height_px = int(rect.height)

            # Estimate DPI from mediabox (assume A4 = 210×297mm if no info)
            dpi = _estimate_dpi(page)

            # Extract text layer
            text = page.get_text("text")
            has_text = bool(text.strip())

            # Detect legacy fonts
            fonts = _get_page_fonts(page)
            legacy = [f for f in fonts if _is_legacy_font(f)]
            text_valid = has_text and not legacy

            # If text layer exists but is legacy-font gibberish, flag it
            if has_text and legacy:
                text_valid = False
                legacy_font_pages.append(page_num)
                issues.append(Issue(
                    id=f"s0_legacy_font_p{page_num}",
                    stage=self.name,
                    page=page_num,
                    severity=IssueSeverity.WARNING,
                    message=f"Legacy Hindi fonts detected: {', '.join(legacy)}. "
                            f"Text layer will be ignored, OCR will be used instead.",
                    evidence={"fonts": legacy},
                ))

            # Additional text-layer validation: check Devanagari content
            if has_text and not legacy:
                dev_ratio = _devanagari_ratio(text)
                # If the PDF claims to have Hindi but we see no Devanagari,
                # the text layer might still be bad
                if dev_ratio < MIN_DEVANAGARI_RATIO and len(text) > 100:
                    # Not necessarily invalid — could be English-only pages
                    pass

            # Classify the page
            classification = _classify_page(page, text, page_num, total_pages)

            # Classify processing path (O2.1): Path A (digital), Path B (scanned), Path C (broken font)
            processing_path = _classify_processing_path(page, text, has_text, legacy)

            # Detect blur (Laplacian variance on the rendered image)
            # Deferred to a helper that works on the rendered pixmap
            blur_score = 0.0

            # Render page image
            image_path = _render_page_image(
                page, pages_dir, page_num, DEFAULT_RENDER_DPI,
            )

            # Compute blur on the rendered image
            blur_score = _compute_blur_score(image_path)

            info = PageInfo(
                page_number=page_num,
                dpi=dpi,
                width_px=width_px,
                height_px=height_px,
                blur_score=blur_score,
                classification=classification,
                processing_path=processing_path,
                has_text_layer=has_text,
                text_layer_valid=text_valid,
                legacy_fonts=legacy,
                watermark_tier=WatermarkTier.W0_NONE,  # Detected in S2
                column_count=_estimate_columns(page),
                image_path=str(image_path.relative_to(ctx.run_dir)),
            )
            pages.append(info)

            # Initialize page status
            ctx.document.page_statuses[page_num] = PageStatus.DONE

            logger.debug(
                "  Page %d: %dx%d, DPI=%.0f, text=%s, class=%s",
                page_num, width_px, height_px, dpi or 0,
                "valid" if text_valid else ("legacy" if legacy else "none"),
                classification.value,
            )

        # Harvest metadata from cover/instruction pages
        metadata = _harvest_metadata(doc, pages, metadata)
        if not metadata.exam_name and ctx.resolved_profile and ctx.resolved_profile.name:
            metadata.exam_name = ctx.resolved_profile.name

        doc.close()

        # Update document
        ctx.document.pages = pages
        ctx.document.metadata = metadata

        # Metrics
        question_pages = [p for p in pages if p.classification == PageClassification.QUESTIONS]
        metrics.update({
            "question_pages": len(question_pages),
            "text_layer_pages": sum(1 for p in pages if p.has_text_layer),
            "valid_text_pages": sum(1 for p in pages if p.text_layer_valid),
            "legacy_font_pages": len(legacy_font_pages),
            "source_type": metadata.source_type or "unknown",
        })

        logger.info(
            "  Intake complete: %d question pages, %d with valid text layer",
            metrics["question_pages"],
            metrics["valid_text_pages"],
        )

        return StageResult(
            document=ctx.document,
            metrics=metrics,
            issues=issues,
        )

    def validate_postconditions(self, result: StageResult) -> list[str]:
        violations = []
        doc = result.document
        if not doc.pages:
            violations.append("No pages extracted from the document")
        question_pages = [p for p in doc.pages if p.classification == PageClassification.QUESTIONS]
        if not question_pages:
            violations.append("No question pages identified — check page classification")
        return violations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_source_type(doc: fitz.Document) -> str:
    """Classify the source as digital, scan, photo, or mixed."""
    has_text = 0
    has_images = 0
    for page in doc:
        if page.get_text("text").strip():
            has_text += 1
        if page.get_images():
            has_images += 1

    total = len(doc)
    if has_text == total:
        return "digital"
    if has_text == 0 and has_images == total:
        return "scan"
    if has_text > 0 and has_images > 0:
        return "mixed"
    return "unknown"


def _estimate_dpi(page: fitz.Page) -> float:
    """Estimate the DPI of a page from its dimensions or embedded images."""
    rect = page.rect
    # If the page contains embedded images (e.g. scanned page), check native image resolution
    try:
        images = page.get_images()
        if images:
            max_img_dpi = 0.0
            doc = page.parent
            for img in images:
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    img_w = base_image.get("width", 0)
                    if rect.width > 0 and img_w > 0:
                        img_dpi = (img_w / rect.width) * 72.0
                        if img_dpi > max_img_dpi:
                            max_img_dpi = img_dpi
                except Exception:
                    pass
            if max_img_dpi >= 100.0:
                return round(max_img_dpi, 1)
    except Exception:
        pass

    return 72.0


def _get_page_fonts(page: fitz.Page) -> list[str]:
    """Get unique font names used on a page."""
    fonts = set()
    for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if block.get("type") == 0:  # text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    if font:
                        fonts.add(font)
    return list(fonts)


def _is_legacy_font(font_name: str) -> bool:
    """Check if a font name matches known legacy Hindi fonts."""
    lower = font_name.lower().strip()
    return any(legacy in lower for legacy in LEGACY_HINDI_FONTS)


def _devanagari_ratio(text: str) -> float:
    """Fraction of characters that are Devanagari."""
    if not text:
        return 0.0
    devanagari = sum(
        1 for ch in text
        if unicodedata.category(ch).startswith("L")
        and "\u0900" <= ch <= "\u097F"
    )
    total_letters = sum(1 for ch in text if unicodedata.category(ch).startswith("L"))
    return devanagari / total_letters if total_letters > 0 else 0.0


def _classify_page(
    page: fitz.Page,
    text: str,
    page_num: int,
    total_pages: int,
) -> PageClassification:
    """
    Heuristic page classification.

    M1 heuristics — will be replaced by template matching in M4:
    - First page with exam title keywords → cover
    - Pages with "instructions" or "read carefully" → instructions
    - Pages with "rough work" or "space for rough work" → rough_work
    - Pages with question-number patterns → questions
    - Nearly blank pages → blank
    """
    lower = text.lower().strip()

    if not lower or len(lower) < 20:
        return PageClassification.BLANK

    # Cover detection
    if page_num <= 2:
        cover_keywords = ["question paper", "exam", "test booklet", "question booklet",
                          "entrance", "jee", "neet", "upsc", "mock test"]
        if any(kw in lower for kw in cover_keywords):
            return PageClassification.COVER

    # Instructions
    instruction_keywords = ["instructions", "read the following", "read carefully",
                            "general instructions", "important instructions",
                            "do not open", "please read"]
    if any(kw in lower for kw in instruction_keywords):
        return PageClassification.INSTRUCTIONS

    # Answer key
    answer_keywords = ["answer key", "answer sheet", "correct answer", "correct option"]
    if any(kw in lower for kw in answer_keywords):
        return PageClassification.ANSWER_KEY

    # Question pages: look for numbered patterns like "1.", "Q.1", "(1)", "Q1."
    # Check BEFORE rough work — Indian exams put "Space for Rough Work" on
    # every question page as a footer, so that keyword alone is not sufficient.
    q_pattern = re.compile(r"(?:^|\n)\s*(?:Q\.?\s*)?(\d{1,3})\s*[.):]", re.MULTILINE)
    matches = q_pattern.findall(lower)
    if len(matches) >= 2:
        return PageClassification.QUESTIONS

    # Rough work: only if the page is *mostly* blank (just the label, no questions)
    if ("rough work" in lower or "space for rough" in lower) and len(lower) < 300:
        return PageClassification.ROUGH_WORK

    # Default: if it has substantial text, assume questions
    if len(lower) > 200:
        return PageClassification.QUESTIONS

    return PageClassification.UNKNOWN


def _estimate_columns(page: fitz.Page) -> int:
    """
    Estimate number of text columns on a page.

    Heuristic: extract text blocks, check if they cluster into
    distinct horizontal bands.
    """
    blocks = page.get_text("blocks")
    if len(blocks) < 3:
        return 1

    # Get x-centers of all text blocks
    x_centers = []
    page_width = page.rect.width
    for block in blocks:
        if block[6] == 0:  # text block
            x_center = (block[0] + block[2]) / 2
            x_centers.append(x_center)

    if not x_centers:
        return 1

    # If most blocks are in the left half or right half, it's 2 columns
    mid = page_width / 2
    left = sum(1 for x in x_centers if x < mid * 0.8)
    right = sum(1 for x in x_centers if x > mid * 1.2)
    total = len(x_centers)

    if left > 0 and right > 0 and (left + right) > total * 0.6:
        return 2

    return 1


def _render_page_image(
    page: fitz.Page,
    output_dir: Path,
    page_num: int,
    dpi: int,
) -> Path:
    """Render a page to a PNG image at the specified DPI."""
    zoom = dpi / 72.0  # PDF points are 72 per inch
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    filename = f"page_{page_num:03d}.png"
    output_path = output_dir / filename
    pix.save(str(output_path))

    return output_path


def _compute_blur_score(image_path: Path) -> float:
    """
    Compute a blur score using Laplacian variance.

    Higher values = sharper image. Typical thresholds:
    - < 50: very blurry
    - 50-100: moderately blurry
    - > 100: acceptably sharp
    """
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(image_path).convert("L")  # Grayscale
        arr = np.array(img, dtype=np.float64)

        # Laplacian kernel
        laplacian = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)

        # Convolve (simple, no scipy dependency)
        from numpy.lib.stride_tricks import sliding_window_view
        windows = sliding_window_view(arr, (3, 3))
        conv = np.sum(windows * laplacian, axis=(-2, -1))
        variance = float(np.var(conv))

        return round(variance, 2)
    except Exception:
        # If image processing fails, return 0 (unknown)
        return 0.0


def _harvest_metadata(
    doc: fitz.Document,
    pages: list[PageInfo],
    metadata: ExamMetadata,
) -> ExamMetadata:
    """
    Extract exam metadata from cover/instruction pages.

    Looks for exam name, year, series code, date, subject.
    This metadata goes into the manifest, never into the HTML output.
    """
    # Check first 3 pages for metadata
    for page_idx in range(min(3, len(doc))):
        page = doc[page_idx]
        text = page.get_text("text")
        if not text:
            continue

        # Year: look for 4-digit year
        year_match = re.search(r"\b(20[12]\d)\b", text)
        if year_match and not metadata.year:
            metadata.year = int(year_match.group(1))

        # Date: look for DD-MM-YYYY or DD/MM/YYYY
        date_match = re.search(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b", text)
        if date_match and not metadata.date:
            metadata.date = date_match.group(1)

        # Exam name detection
        exam_patterns = [
            (r"(?:NEET|National Eligibility.*Entrance)", "NEET"),
            (r"(?:JEE\s*(?:Main|Advanced|Adv))", "JEE"),
            (r"(?:UPSC|Union Public Service)", "UPSC"),
            (r"(?:AIIMS)", "AIIMS"),
        ]
        for pattern, name in exam_patterns:
            if re.search(pattern, text, re.IGNORECASE) and not metadata.exam_name:
                metadata.exam_name = name

        # Series code: single letter like "Set A", "Code D", "Series X"
        series_match = re.search(r"(?:Set|Code|Series|Paper)\s*[-:]?\s*([A-Z])\b", text, re.IGNORECASE)
        if series_match and not metadata.series_code:
            metadata.series_code = series_match.group(1).upper()

        # Subject detection
        subject_patterns = [
            (r"\bPhysics\b", "Physics"),
            (r"\bChemistry\b", "Chemistry"),
            (r"\bMathematics?\b", "Mathematics"),
            (r"\bBiology\b", "Biology"),
            (r"\bBotany\b", "Botany"),
            (r"\bZoology\b", "Zoology"),
        ]
        for pattern, subj in subject_patterns:
            if re.search(pattern, text, re.IGNORECASE) and not metadata.subject:
                metadata.subject = subj

    return metadata


def _classify_processing_path(
    page: fitz.Page,
    text: str,
    has_text: bool,
    legacy_fonts: list[str],
) -> PageProcessingPath:
    """
    Classify page into:
    - Path A: digital with valid text layer (standard fonts, plausible scripts)
    - Path B: scanned/raster (no usable text layer)
    - Path C: digital but broken fonts (Type3, missing ToUnicode, legacy 8-bit Hindi fonts)
    """
    if legacy_fonts:
        return PageProcessingPath.PATH_C

    clean_text = text.strip() if text else ""
    if not has_text or len(clean_text) < 10:
        return PageProcessingPath.PATH_B

    # Inspect fonts for Type3, missing ToUnicode, or bitmap fonts
    fonts = _get_page_fonts(page)
    for f in fonts:
        f_lower = f.lower()
        if "type3" in f_lower or "pk" in f_lower:
            return PageProcessingPath.PATH_C

    # Check replacement character and Private Use Area (PUA) ratios
    if clean_text:
        pua_or_replace = sum(
            1 for ch in clean_text if ch == "\ufffd" or 0xE000 <= ord(ch) <= 0xF8FF
        )
        if (pua_or_replace / max(1, len(clean_text))) >= 0.05:
            return PageProcessingPath.PATH_C

    return PageProcessingPath.PATH_A

