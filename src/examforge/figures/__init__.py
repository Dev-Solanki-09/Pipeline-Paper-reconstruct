"""ExamForge figures package: vector-first extraction, ink-aware crop, and association."""

from __future__ import annotations

from examforge.figures.associate import (
    associate_figures_to_questions,
    score_figure_question_match,
)
from examforge.figures.cleanup import remove_black_borders
from examforge.figures.crop import (
    calculate_border_strip_ink_ratio,
    refine_bbox,
    shrink_to_ink,
)
from examforge.figures.raster import extract_raster_figures
from examforge.figures.resolution import (
    classify_scale_class,
    compute_target_dpi,
)
from examforge.figures.vector import (
    VectorCluster,
    cluster_drawings,
    compute_path_signature,
    extract_vector_figures,
    find_repeated_vector_signatures,
    is_separator_rule,
)

__all__ = [
    "VectorCluster",
    "associate_figures_to_questions",
    "calculate_border_strip_ink_ratio",
    "classify_scale_class",
    "cluster_drawings",
    "compute_path_signature",
    "compute_target_dpi",
    "extract_raster_figures",
    "extract_vector_figures",
    "find_repeated_vector_signatures",
    "is_separator_rule",
    "refine_bbox",
    "remove_black_borders",
    "score_figure_question_match",
    "shrink_to_ink",
]
