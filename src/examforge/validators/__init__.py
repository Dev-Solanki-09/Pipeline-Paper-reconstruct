"""Validators package: exposes registry, Validator Protocol, CostTier, and registers all spec rule checks."""

from __future__ import annotations

from examforge.validators import (
    furniture_branding,
    language_consistency,
    packaged_output_check,
    r01_no_furniture,
    r02_no_branding,
    r03_no_watermark,
    r04_continuous,
    r05_bilingual,
    r06_complete,
    r07_formulas,
    r08_figures,
    r09_unicode,
    r10_language_consistency,
    r11_text_layer_agreement,
    r12_lexicon,
    r13_render_check,
    r14_sequence_gaps,
    r15_structure_consistency,
    r16_answer_binding,
    structure_integrity,
)
from examforge.validators.base import CostTier, FunctionValidator, Validator
from examforge.validators.registry import (
    VALIDATOR_ALIASES,
    get_canonical_validator_name,
    get_validator,
    get_validator_tier,
    list_validators,
    register_validator,
)

__all__ = [
    "Validator",
    "FunctionValidator",
    "CostTier",
    "get_validator",
    "get_validator_tier",
    "get_canonical_validator_name",
    "list_validators",
    "register_validator",
    "VALIDATOR_ALIASES",
    # Consolidated modules (Phase O4.2)
    "furniture_branding",
    "language_consistency",
    "packaged_output_check",
    "structure_integrity",
    # Backward compatible adapters
    "r01_no_furniture",
    "r02_no_branding",
    "r03_no_watermark",
    "r04_continuous",
    "r05_bilingual",
    "r06_complete",
    "r07_formulas",
    "r08_figures",
    "r09_unicode",
    "r10_language_consistency",
    "r11_text_layer_agreement",
    "r12_lexicon",
    "r13_render_check",
    "r14_sequence_gaps",
    "r15_structure_consistency",
    "r16_answer_binding",
]
