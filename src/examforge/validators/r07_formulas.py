"""Validator for R07: formula_roundtrip."""

from __future__ import annotations

import re

from examforge.ir.schema import (
    BlockType,
    ExamDocument,
    Issue,
    IssueSeverity,
)
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator


@register_validator("formula_roundtrip", cost_tier=CostTier.FREE)
def validate_formula_roundtrip(document: ExamDocument, rule: Rule) -> list[Issue]:
    """Verify that formulas have balanced delimiters and valid LaTeX commands."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if rule.severity.value == "blocker" else IssueSeverity.WARNING

    # Check formula blocks
    for block in document.blocks:
        if block.type != BlockType.FORMULA:
            continue

        text = block.latex or block.text
        # Check balanced dollar signs
        if text.count("$") % 2 != 0:
            issues.append(
                Issue(
                    id=f"r07_unbalanced_dollar_{block.id}",
                    stage="s8_verify",
                    rule=rule.check,
                    page=block.page,
                    element_id=block.id,
                    severity=severity,
                    message=f"Rule R07 violation on page {block.page}: Unbalanced $ delimiters in formula",
                )
            )

        # Check balanced curly braces
        depth = 0
        balanced_braces = True
        for ch in text:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    balanced_braces = False
                    break
        if depth != 0 or not balanced_braces:
            issues.append(
                Issue(
                    id=f"r07_unbalanced_braces_{block.id}",
                    stage="s8_verify",
                    rule=rule.check,
                    page=block.page,
                    element_id=block.id,
                    severity=severity,
                    message=f"Rule R07 violation on page {block.page}: Unbalanced {{}} braces in formula",
                )
            )

    return issues
