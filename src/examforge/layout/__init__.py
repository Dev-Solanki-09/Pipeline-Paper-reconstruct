"""
Layout and structure generalization engine for ExamForge v2 (Phase 6).

Provides column detection, reading order, numbering, nesting, passages,
question-kind classification, document parts, and language layouts.
"""

from __future__ import annotations

from examforge.layout.columns import (
    ColumnInfo,
    ColumnLayout,
    ColumnSpan,
    SpanType,
    detect_columns,
)
from examforge.layout.kinds import classify_question_kind
from examforge.layout.languages import (
    AlignedBilingualQuestion,
    align_language_layout,
)
from examforge.layout.nesting import (
    SubPart,
    detect_internal_choice,
    detect_subparts,
)
from examforge.layout.numbering import (
    NumberingEngine,
    ParsedQuestionStart,
    is_chemical_formula_or_prose_ref,
    is_valid_monotonic_step,
    parse_options_from_text,
)
from examforge.layout.orientation import (
    detect_page_orientation,
    detect_two_up_spread,
    split_two_up_blocks,
)
from examforge.layout.parts import (
    classify_document_part,
    classify_page_part,
)
from examforge.layout.passages import (
    PassageSegment,
    detect_passages,
    link_questions_to_passages,
)
from examforge.layout.reading_order import order_blocks
from examforge.layout.redos import SafeRegex, compile_safe_regex, validate_pattern_safety

__all__ = [
    "ColumnInfo",
    "ColumnLayout",
    "ColumnSpan",
    "SpanType",
    "detect_columns",
    "order_blocks",
    "NumberingEngine",
    "ParsedQuestionStart",
    "is_chemical_formula_or_prose_ref",
    "is_valid_monotonic_step",
    "parse_options_from_text",
    "SubPart",
    "detect_internal_choice",
    "detect_subparts",
    "PassageSegment",
    "detect_passages",
    "link_questions_to_passages",
    "classify_question_kind",
    "classify_page_part",
    "classify_document_part",
    "AlignedBilingualQuestion",
    "align_language_layout",
    "detect_page_orientation",
    "detect_two_up_spread",
    "split_two_up_blocks",
    "SafeRegex",
    "compile_safe_regex",
    "validate_pattern_safety",
]
