"""Validator registry for ExamForge spec rules (Phase O4.1 & O4.2)."""

from __future__ import annotations

from typing import Callable, Optional

from examforge.ir.schema import ExamDocument, Issue
from examforge.spec import Rule
from examforge.validators.base import CostTier

from examforge.registry import validators as _CANONICAL_VALIDATORS

ValidatorFn = Callable[[ExamDocument, Rule], list[Issue]]

_REGISTRY: dict[str, ValidatorFn] = {}
_COST_TIERS: dict[str, CostTier] = {}

VALIDATOR_ALIASES: dict[str, str] = {
    # R01 + R02 -> furniture_branding
    "no_headers_footers_page_numbers": "furniture_branding",
    "no_brand_text_or_logo": "furniture_branding",
    "r01_no_furniture": "furniture_branding",
    "r02_no_branding": "furniture_branding",
    "R01_no_furniture": "furniture_branding",
    "R02_no_branding": "furniture_branding",

    # R04 + R13 -> packaged_output_check
    "no_page_wrappers_or_breaks": "packaged_output_check",
    "render_check": "packaged_output_check",
    "r04_continuous": "packaged_output_check",
    "r13_render_check": "packaged_output_check",
    "R04_continuous": "packaged_output_check",
    "R13_render_check": "packaged_output_check",

    # R05 + R10 -> language_consistency
    "en_hi_pairs_complete": "language_consistency",
    "r05_bilingual": "language_consistency",
    "r10_language_consistency": "language_consistency",
    "R05_bilingual": "language_consistency",
    "R10_language_consistency": "language_consistency",

    # R06 + R14 + R15 -> structure_integrity
    "numbering_continuity": "structure_integrity",
    "sequence_gaps": "structure_integrity",
    "structure_consistency": "structure_integrity",
    "r06_complete": "structure_integrity",
    "r14_sequence_gaps": "structure_integrity",
    "r15_structure_consistency": "structure_integrity",
    "R06_complete": "structure_integrity",
    "R14_sequence_gaps": "structure_integrity",
    "R15_structure_consistency": "structure_integrity",

    # R16 -> answer_binding
    "R16_answer_binding": "answer_binding",
    "r16_answer_binding": "answer_binding",
}


def get_canonical_validator_name(name: str) -> str:
    """Return the canonical validator check name resolving aliases."""
    return VALIDATOR_ALIASES.get(name, name)


def register_validator(
    name: str,
    cost_tier: CostTier = CostTier.FREE,
    aliases: list[str] | None = None,
):
    """Decorator to register a validator function by check name with cost tier and aliases."""
    def decorator(fn: ValidatorFn):
        _REGISTRY[name] = fn
        _COST_TIERS[name] = cost_tier
        _CANONICAL_VALIDATORS.register(
            name,
            fn,
            tags={"cost_tier": cost_tier},
            allow_replace=True,
        )
        if aliases:
            for alias in aliases:
                VALIDATOR_ALIASES[alias] = name
        return fn
    return decorator


def get_validator(name: str) -> Optional[ValidatorFn]:
    """Retrieve validator by check name or rule ID, resolving aliases."""
    if name in _REGISTRY:
        return _REGISTRY[name]
    canonical = get_canonical_validator_name(name)
    if canonical in _CANONICAL_VALIDATORS:
        return _CANONICAL_VALIDATORS.get(canonical)
    if name in _CANONICAL_VALIDATORS:
        return _CANONICAL_VALIDATORS.get(name)
    fn = _REGISTRY.get(canonical)
    if fn is not None:
        return fn
    return _REGISTRY.get(name)


def get_validator_tier(name: str) -> CostTier:
    """Get the cost tier for a validator, default to FREE."""
    if name in _COST_TIERS:
        return _COST_TIERS[name]
    canonical = get_canonical_validator_name(name)
    if canonical in _CANONICAL_VALIDATORS:
        entry = _CANONICAL_VALIDATORS.get_entry(canonical)
        return entry.tags.get("cost_tier", _COST_TIERS.get(canonical, CostTier.FREE))
    return _COST_TIERS.get(canonical, CostTier.FREE)


def list_validators() -> list[str]:
    """List all primary registered validator names."""
    canonical_list = _CANONICAL_VALIDATORS.list()
    if canonical_list:
        return canonical_list
    return sorted(list(_REGISTRY.keys()))
