"""Repair escalation router mapping issues to appropriate repair tiers (Phase O5)."""

from __future__ import annotations

from enum import StrEnum
import logging
from typing import Any

from examforge.ir.schema import Issue, IssueSeverity, Question

logger = logging.getLogger(__name__)


class RepairTier(StrEnum):
    """Hierarchical repair tiers ordered by cost and invasiveness."""

    T0 = "T0"  # Deterministic fix (lexicon, split, gap re-search)
    T1 = "T1"  # Local second opinion (higher DPI re-render, second OCR engine)
    T2 = "T2"  # Cheap VLM candidate chooser (returns 1 index or None)
    T3 = "T3"  # Strong model constrained JSON patch
    T4 = "T4"  # Human review (EXIT_NEEDS_REVIEW)


DEFAULT_TIER_LADDER: dict[str, list[RepairTier]] = {
    "lexicon": [RepairTier.T0, RepairTier.T2, RepairTier.T3, RepairTier.T4],
    "sequence_gaps": [RepairTier.T0, RepairTier.T1, RepairTier.T3, RepairTier.T4],
    "text_layer_agreement": [
        RepairTier.T0,
        RepairTier.T1,
        RepairTier.T2,
        RepairTier.T3,
        RepairTier.T4,
    ],
    "formulas": [RepairTier.T1, RepairTier.T3, RepairTier.T4],
    "figures": [RepairTier.T1, RepairTier.T3, RepairTier.T4],
    "default": [
        RepairTier.T0,
        RepairTier.T1,
        RepairTier.T2,
        RepairTier.T3,
        RepairTier.T4,
    ],
}


def is_llm_eligible(issue: Issue, question: Question | None) -> tuple[bool, str]:
    """
    O5.2: LLM-eligible issues only:
    BLOCKER severity AND localized crop/pages AND candidates or target text available.
    WARN and low-evidence issues never reach T2/T3.
    """
    if issue.severity != IssueSeverity.BLOCKER:
        return False, "Issue severity is not BLOCKER"

    if question is None:
        return False, "No target question associated with issue"

    # Check for localized context (crop, bbox, page neighborhood, or source pages)
    ev = issue.evidence or {}
    has_loc = (
        bool(ev.get("crop"))
        or bool(ev.get("bbox"))
        or bool(ev.get("page_neighborhood"))
        or bool(question.source_pages)
        or bool(issue.page)
    )
    if not has_loc:
        return False, "No localized spatial crop or page bounds available"

    # Check for candidates or target text to repair
    has_candidates = bool(issue.candidates) or bool(ev.get("candidates")) or bool(ev.get("missing_questions"))
    has_text = bool(question.stem_text_en) or bool(question.stem_text_hi) or bool(question.options)
    if not (has_candidates or has_text):
        return False, "No candidate tokens or question text available for repair"

    return True, ""


class RepairRouter:
    """Routes an issue to an appropriate tier based on rule type and attempt count."""

    def __init__(
        self,
        matrix: dict[str, list[RepairTier]] | None = None,
    ) -> None:
        self.matrix = matrix or DEFAULT_TIER_LADDER

    def route(
        self,
        issue: Issue,
        attempt: int = 0,
        budget_exhausted: bool = False,
        offline_mode: bool = False,
        disabled_tiers: set[RepairTier] | None = None,
    ) -> RepairTier:
        """Determine next repair tier for an issue."""
        if budget_exhausted:
            return RepairTier.T4

        rule_name = issue.rule or "default"
        ladder = list(self.matrix.get(rule_name, self.matrix["default"]))

        if offline_mode:
            # Exclude remote AI model calls
            ladder = [t for t in ladder if t not in (RepairTier.T2, RepairTier.T3)]

        if disabled_tiers:
            ladder = [t for t in ladder if t not in disabled_tiers]

        if attempt >= len(ladder):
            return RepairTier.T4

        return ladder[attempt]
