"""Validator for R08: figure_clean_border_and_present."""

from __future__ import annotations

import re

from examforge.ir.schema import (
    ExamDocument,
    Issue,
    IssueSeverity,
)
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

_FIGURE_REF_RE = re.compile(
    r"\b(?:figure|fig\.?|given below|diagram|shown below|circuit)\b",
    re.IGNORECASE,
)


@register_validator("figure_clean_border_and_present", cost_tier=CostTier.IO)
def validate_figures_present(document: ExamDocument, rule: Rule) -> list[Issue]:
    """Verify that questions referencing diagrams or figures have valid figure references."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if rule.severity.value == "blocker" else IssueSeverity.WARNING

    for q in document.questions:
        stem = q.stem_text_en + " " + q.stem_text_hi
        if _FIGURE_REF_RE.search(stem):
            # Question explicitly mentions a figure or diagram
            if not q.figure_refs:
                issues.append(
                    Issue(
                        id=f"r08_missing_fig_{q.id}",
                        stage="s8_verify",
                        rule=rule.check,
                        element_id=q.id,
                        severity=severity,
                        message=f"Rule R08 violation: Question {q.number} references a figure/diagram but has no assigned figures",
                    )
                )

    return issues
