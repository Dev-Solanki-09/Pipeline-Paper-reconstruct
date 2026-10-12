"""
S6 Figures: Extract, classify, and assign figures to questions.

This stage:
1. Iterates over question pages in the PDF document.
2. Extracts embedded raster images using PyMuPDF Pixmap.
3. Classifies figures (filters out tiny icons and decorative lines).
4. Saves extracted figures as clean PNGs in stages/s6_figures/figures/.
5. Assigns each figure to its corresponding question based on page and vertical coordinates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from examforge.ir.schema import (
    BBox,
    BlockStatus,
    Figure,
    FigureClass,
    PageClassification,
    Question,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

MIN_FIGURE_DIMENSION = 50
MAX_ASPECT_RATIO = 5.0


class S6Figures(Stage):
    """
    Stage 6: Figure detection, extraction, and assignment to questions.
    """

    name = "s6_figures"

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S6 requires pages and questions to be populated."""
        violations = []
        if not ctx.document.pages:
            violations.append("No pages found in document -- S0 Intake must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues = []
        metrics: dict = {}

        source_path = Path(doc.source_path)
        if not source_path.exists():
            return StageResult(document=doc, metrics={"figures_extracted": 0}, issues=issues)

        pdf_doc = fitz.open(str(source_path))

        figures_dir = ctx.stage_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)

        all_figures: list[Figure] = []
        question_page_numbers = {
            p.page_number
            for p in doc.pages
            if p.classification == PageClassification.QUESTIONS
        }

        # If no question pages classified, consider all non-cover pages
        if not question_page_numbers:
            question_page_numbers = {
                p.page_number
                for p in doc.pages
                if p.classification not in (PageClassification.COVER, PageClassification.ROUGH_WORK, PageClassification.BLANK)
            }

        img_counter = 0
        for page_info in doc.pages:
            page_num = page_info.page_number
            if page_num not in question_page_numbers:
                continue

            page_idx = page_num - 1
            if page_idx >= len(pdf_doc):
                continue

            page = pdf_doc[page_idx]
            page_figures, img_counter = _extract_embedded_images(
                pdf_doc, page, page_num, figures_dir, img_counter
            )
            all_figures.extend(page_figures)

        pdf_doc.close()

        # Assign figures to questions
        if doc.questions:
            _assign_figures_to_questions(all_figures, doc.questions)

        doc.figures = all_figures

        metrics["figures_extracted"] = len(all_figures)
        metrics["figures_assigned"] = sum(1 for f in all_figures if f.question_ref)

        logger.info(
            "  S6 Figures complete: %d figures extracted, %d assigned to questions",
            len(all_figures),
            metrics["figures_assigned"],
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Verify figures have valid bounding boxes and crop paths."""
        violations = []
        for fig in result.document.figures:
            if fig.bbox.width <= 0 or fig.bbox.height <= 0:
                violations.append(f"Figure {fig.id} has invalid bbox dimensions.")
            if fig.crop_path and not Path(fig.crop_path).exists():
                violations.append(f"Figure {fig.id} crop file does not exist at {fig.crop_path}.")
        return violations


def _classify_figure(
    width: int,
    height: int,
    image_data: bytes | None = None,
) -> FigureClass | None:
    """Classify a figure. Returns None if it should be skipped.

    Rules:
    - Images smaller than 50x50 px -> None (skip icons, bullets)
    - Aspect ratio > 5:1 (or < 1:5) -> None (skip lines, rules)
    - Otherwise -> FigureClass.DIAGRAM
    """
    if width < MIN_FIGURE_DIMENSION or height < MIN_FIGURE_DIMENSION:
        return None

    aspect = max(width / height, height / width)
    if aspect > MAX_ASPECT_RATIO:
        return None

    return FigureClass.DIAGRAM


def _extract_embedded_images(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    output_dir: Path,
    img_counter: int = 0,
) -> tuple[list[Figure], int]:
    """Extract embedded images from a PDF page."""
    figures: list[Figure] = []
    seen_xrefs = set()

    image_list = page.get_images(full=True)
    for img_info in image_list:
        xref = img_info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        try:
            pix = fitz.Pixmap(doc, xref)
        except Exception as e:
            logger.debug("Failed to extract pixmap for xref %d: %s", xref, e)
            continue

        # Convert to RGB if needed (e.g. CMYK or alpha)
        if pix.n >= 5:
            pix = fitz.Pixmap(fitz.csRGB, pix)

        classification = _classify_figure(pix.width, pix.height)
        if classification is None:
            continue

        rects = page.get_image_rects(xref)
        if not rects:
            continue

        for rect in rects:
            # Skip images located strictly in footer rough work area
            if rect.y0 > page.rect.height * 0.88:
                continue

            fig_id = f"fig_{page_num}_{img_counter}"
            img_counter += 1
            filename = f"{fig_id}.png"
            crop_path = output_dir / filename

            pix.save(str(crop_path))

            # Calculate mm dimensions for print styling (72 pt = 25.4 mm)
            width_mm = round((rect.width / 72.0) * 25.4, 1)
            height_mm = round((rect.height / 72.0) * 25.4, 1)

            fig = Figure(
                id=fig_id,
                page=page_num,
                bbox=BBox(
                    x1=int(round(rect.x0)),
                    y1=int(round(rect.y0)),
                    x2=int(round(rect.x1)),
                    y2=int(round(rect.y1)),
                ),
                crop_path=str(crop_path),
                format="png",
                classification=classification,
                width_mm=width_mm,
                height_mm=height_mm,
                status=BlockStatus.TRUSTED,
            )
            figures.append(fig)

    return figures, img_counter


def _assign_figures_to_questions(
    figures: list[Figure],
    questions: list[Question],
) -> None:
    """Assign each figure to its nearest question (mutates both)."""
    for figure in figures:
        # Candidate questions on the same page
        same_page_questions = [
            q for q in questions if figure.page in q.source_pages
        ]

        if not same_page_questions:
            continue

        # Sort candidate questions by their vertical start position on this page
        def _get_q_y_span(q: Question) -> tuple[float, float]:
            page_blocks = [b for b in q.stem_en if b.page == figure.page]
            if not page_blocks:
                return (0.0, 9999.0)
            y_min = min(b.bbox.y1 for b in page_blocks)
            y_max = max(b.bbox.y2 for b in page_blocks)
            return (y_min, y_max)

        best_q: Optional[Question] = None
        min_distance = float("inf")

        fig_y = figure.bbox.y1

        for i, q in enumerate(same_page_questions):
            y_min, y_max = _get_q_y_span(q)
            # If figure is inside or immediately following question stem
            if y_min <= fig_y <= y_max:
                best_q = q
                break

            # If figure is between this question and next question
            next_y_min = float("inf")
            if i + 1 < len(same_page_questions):
                next_y_min, _ = _get_q_y_span(same_page_questions[i + 1])

            if y_min <= fig_y < next_y_min:
                best_q = q
                break

            dist = abs(fig_y - y_min)
            if dist < min_distance:
                min_distance = dist
                best_q = q

        if best_q is not None:
            figure.question_ref = best_q.id
            if figure.id not in best_q.figure_refs:
                best_q.figure_refs.append(figure.id)
