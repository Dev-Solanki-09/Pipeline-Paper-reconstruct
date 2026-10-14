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

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["figures", "crop_extractor"]

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

        # Check feature flag
        use_figures_v2 = True
        if ctx.profile and hasattr(ctx.profile, "flags") and ctx.profile.flags is not None:
            use_figures_v2 = ctx.profile.flags.get("figures_v2", True)
        elif ctx.config and hasattr(ctx.config, "flags") and ctx.config.flags is not None:
            use_figures_v2 = ctx.config.flags.get("figures_v2", True)

        img_counter = 0

        if not use_figures_v2:
            # v1 rollback logic
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

            # Assign figures to questions (v1)
            if doc.questions:
                _assign_figures_to_questions(all_figures, doc.questions)

            doc.figures = all_figures
            metrics["figures_extracted"] = len(all_figures)
            metrics["figures_assigned"] = sum(1 for f in all_figures if f.question_ref)
            return StageResult(document=doc, metrics=metrics, issues=issues)

        # figures_v2 pipeline
        from examforge.figures.associate import associate_figures_to_questions
        from examforge.figures.vector import (
            extract_vector_figures,
            find_repeated_vector_signatures,
        )

        watermark_sigs = find_repeated_vector_signatures(pdf_doc, min_pages=3)

        for page_info in doc.pages:
            page_num = page_info.page_number
            if page_num not in question_page_numbers:
                continue

            page_idx = page_num - 1
            if page_idx >= len(pdf_doc):
                continue

            page = pdf_doc[page_idx]

            # 1. Embedded raster images
            page_raster_figures, img_counter = _extract_embedded_images(
                pdf_doc, page, page_num, figures_dir, img_counter
            )
            all_figures.extend(page_raster_figures)

            # 2. Vector drawings (circuits, ray diagrams, geometry)
            page_vector_figures = extract_vector_figures(
                doc=pdf_doc,
                page=page,
                page_num=page_num,
                output_dir=figures_dir,
                watermark_signatures=watermark_sigs,
                img_counter_start=img_counter,
            )
            img_counter += len(page_vector_figures)
            all_figures.extend(page_vector_figures)

        pdf_doc.close()

        # Multi-signal association
        if doc.questions:
            assoc_issues = associate_figures_to_questions(
                figures=all_figures,
                questions=doc.questions,
                blocks=doc.blocks,
                allow_proportional_fallback=False,
            )
            issues.extend(assoc_issues)

        doc.figures = all_figures

        metrics["figures_extracted"] = len(all_figures)
        metrics["figures_assigned"] = sum(1 for f in all_figures if f.question_ref)

        logger.info(
            "  S6 Figures v2 complete: %d figures extracted, %d assigned to questions",
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


def _determine_scale_class(width_px: int, height_px: int) -> str:
    """Map figure dimensions to canonical NEET/JEE diagram scale taxonomy:

    - img-inline: tiny inline icons or small symbols (height <= 40)
    - img-opt: option-level diagrams (height <= 65, width <= 220)
    - img-sm: small diagrams (height <= 120, width <= 240)
    - img-wide: wide panoramic graphs or circuits (width/height > 1.8)
    - img-lg: large multi-part diagrams (height >= 280)
    - img-md: standard medium diagrams (default)
    """
    if height_px <= 40:
        return "img-inline"
    if height_px <= 65 and width_px <= 220:
        return "img-opt"
    if height_px <= 120 and width_px <= 240:
        return "img-sm"
    if width_px / max(height_px, 1) > 1.8 and height_px <= 180:
        return "img-wide"
    if height_px >= 280 or width_px >= 340:
        return "img-lg"
    return "img-md"


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

            scale_class = _determine_scale_class(pix.width, pix.height)

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
                scale_class=scale_class,
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

        same_page_questions.sort(key=lambda q: (q.sequence_index or 0, q.number or 0))
        num_qs = len(same_page_questions)

        # Sort candidate questions by their vertical start position on this page
        def _get_q_y_span(q: Question, idx: int) -> tuple[float, float]:
            all_blocks = [b for b in (q.stem_en + q.stem_hi) if b.page == figure.page]
            for opt in q.options:
                all_blocks.extend([b for b in (opt.text_en + opt.text_hi) if b.page == figure.page])

            if all_blocks:
                y_min = min(b.bbox.y1 for b in all_blocks)
                y_max = max(b.bbox.y2 for b in all_blocks)
                return (y_min, y_max)

            # Fallback when blocks are not attached: estimate vertical section on page
            est_h = 842.0 / max(1, num_qs)
            return (idx * est_h, (idx + 1) * est_h)

        best_q: Optional[Question] = None
        min_distance = float("inf")

        fig_y = figure.bbox.y1

        for i, q in enumerate(same_page_questions):
            y_min, y_max = _get_q_y_span(q, i)
            # If figure is inside or immediately following question stem
            if y_min <= fig_y <= y_max:
                best_q = q
                break

            # If figure is between this question and next question
            next_y_min = float("inf")
            if i + 1 < len(same_page_questions):
                next_y_min, _ = _get_q_y_span(same_page_questions[i + 1], i + 1)

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
