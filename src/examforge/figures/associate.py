"""Figure-to-question association: multi-signal scoring and constrained greedy assignment."""

from __future__ import annotations

import re
from typing import Optional

from examforge.ir.schema import (
    Block,
    Figure,
    Issue,
    IssueSeverity,
    Option,
    Question,
)

_FIGURE_CUE_RE = re.compile(
    r"\b(fig(ure)?\.?|diagram|circuit|graph|चित्र|रेखाचित्र|दिए गए चित्र|दिखाए अनुसार|दिखाए गए|shown in (?:the )?(?:figure|diagram|circuit|graph))\b",
    re.IGNORECASE,
)


def _get_question_y_span(q: Question, page_num: int) -> tuple[float, float]:
    """Get the vertical min and max span of a question on a given page."""
    all_blocks: list[Block] = [
        b for b in (q.stem_en + q.stem_hi) if b.page == page_num
    ]
    for opt in q.options:
        all_blocks.extend([b for b in (opt.text_en + opt.text_hi) if b.page == page_num])

    if all_blocks:
        y_min = min(b.bbox.y1 for b in all_blocks)
        y_max = max(b.bbox.y2 for b in all_blocks)
        return float(y_min), float(y_max)

    return 0.0, 842.0


def score_figure_question_match(figure: Figure, question: Question) -> float:
    """Compute a multi-signal score for associating a figure with a question."""
    if figure.page not in question.source_pages:
        return -100.0

    score = 0.0
    q_y1, q_y2 = _get_question_y_span(question, figure.page)
    fig_y1 = float(figure.bbox.y1)
    fig_y2 = float(figure.bbox.y2)

    # 1. Physical vertical placement
    if q_y1 <= fig_y1 <= q_y2:
        # Figure is inside question vertical span
        score += 20.0
    elif fig_y1 >= q_y2:
        # Figure is immediately below question
        dist = fig_y1 - q_y2
        score += max(0.0, 15.0 - (dist / 25.0))
    else:
        # Figure is above question stem
        dist = q_y1 - fig_y2
        score += max(0.0, 10.0 - (dist / 30.0))

    # 2. Text figure cue boost
    stem_text = (question.stem_text_en or "") + " " + (question.stem_text_hi or "")
    if _FIGURE_CUE_RE.search(stem_text):
        score += 12.0

    # 3. Option diagram alignment
    for opt in question.options:
        opt_blocks = [b for b in (opt.text_en + opt.text_hi) if b.page == figure.page]
        if opt_blocks:
            oy1 = min(b.bbox.y1 for b in opt_blocks)
            oy2 = max(b.bbox.y2 for b in opt_blocks)
            if max(oy1, fig_y1) <= min(oy2, fig_y2) + 15 and figure.scale_class == "img-opt":
                score += 20.0
                break

    return score


def associate_figures_to_questions(
    figures: list[Figure],
    questions: list[Question],
    blocks: list[Block] | None = None,
    allow_proportional_fallback: bool = False,
    min_score_threshold: float = 5.0,
) -> list[Issue]:
    """Assign figures to questions using constrained greedy assignment.

    Returns:
        list of Issues emitted for unassigned or ambiguous figures.
    """
    issues: list[Issue] = []

    for figure in figures:
        same_page_questions = [
            q for q in questions if figure.page in q.source_pages
        ]

        if not same_page_questions:
            if not allow_proportional_fallback:
                issues.append(
                    Issue(
                        id=f"unassigned_fig_{figure.id}",
                        stage="s6_figures",
                        rule="figure_association",
                        element_id=figure.id,
                        severity=IssueSeverity.WARNING,
                        message=f"Unassigned figure: Figure {figure.id} on page {figure.page} could not be confidently associated with any question.",
                    )
                )
            continue

        best_q: Optional[Question] = None
        best_score = -float("inf")

        for q in same_page_questions:
            s = score_figure_question_match(figure, q)
            if s > best_score:
                best_score = s
                best_q = q

        if best_q is not None and best_score >= min_score_threshold:
            figure.question_ref = best_q.id
            if figure.id not in best_q.figure_refs:
                best_q.figure_refs.append(figure.id)

            # Check if figure belongs to a specific option with strict vertical baseline ordering (Phase O7)
            all_opt_blocks = [b for o in best_q.options for b in (o.text_en + o.text_hi) if b.page == figure.page]
            min_opt_y1 = min((b.bbox.y1 for b in all_opt_blocks), default=None)

            # A figure preceding the option vertical baseline belongs to the stem, not options
            is_above_options = (min_opt_y1 is not None and figure.bbox.y2 <= min_opt_y1 + 5)

            if not is_above_options:
                for opt in best_q.options:
                    opt_blocks = [b for b in (opt.text_en + opt.text_hi) if b.page == figure.page]
                    if opt_blocks:
                        oy1 = min(b.bbox.y1 for b in opt_blocks)
                        oy2 = max(b.bbox.y2 for b in opt_blocks)
                        # Option figure must overlap horizontally or be horizontally adjacent and within option vertical band
                        if figure.bbox.y1 >= oy1 - 10 and max(oy1, figure.bbox.y1) <= min(oy2, figure.bbox.y2) + 20:
                            if figure.scale_class == "img-opt" or (
                                figure.bbox.height <= 85 and figure.bbox.width <= 250
                            ):
                                figure.option_ref = opt.label
                                opt.figure_ref = figure.id
                                break
        else:
            if allow_proportional_fallback and same_page_questions:
                # Proportional fallback
                fallback_q = same_page_questions[0]
                figure.question_ref = fallback_q.id
                if figure.id not in fallback_q.figure_refs:
                    fallback_q.figure_refs.append(figure.id)
            else:
                issues.append(
                    Issue(
                        id=f"unassigned_fig_{figure.id}",
                        stage="s6_figures",
                        rule="figure_association",
                        element_id=figure.id,
                        severity=IssueSeverity.WARNING,
                        message=f"Unassigned figure: Figure {figure.id} on page {figure.page} could not be confidently associated with any question.",
                    )
                )

    return issues
