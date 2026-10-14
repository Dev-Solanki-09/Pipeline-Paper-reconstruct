"""Validator for R03: watermark_residual."""

from __future__ import annotations

from examforge.ir.schema import (
    BlockStatus,
    ExamDocument,
    Issue,
    IssueSeverity,
    WatermarkTier,
)
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator


@register_validator("watermark_residual", cost_tier=CostTier.IO)
def validate_watermark_residual(document: ExamDocument, rule: Rule) -> list[Issue]:
    """Verify that no baked-in watermark residuals remain in content blocks."""
    issues: list[Issue] = []
    severity = IssueSeverity(rule.severity.value)

    # Check page-level watermark tiers
    for page in document.pages:
        if page.watermark_tier == WatermarkTier.W5_BAKED:
            issues.append(
                Issue(
                    id=f"r03_watermark_p{page.page_number}",
                    stage="s8_verify",
                    rule=rule.check,
                    page=page.page_number,
                    severity=severity,
                    message=f"Rule R03 violation: Page {page.page_number} has baked watermark (W5)",
                )
            )

    return issues
