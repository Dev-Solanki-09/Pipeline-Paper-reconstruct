"""Validator for R09: devanagari_nfc_and_lexicon."""

from __future__ import annotations

import unicodedata

from examforge.ir.schema import (
    BlockStatus,
    ExamDocument,
    Issue,
    IssueSeverity,
)
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator


@register_validator("devanagari_nfc_and_lexicon", cost_tier=CostTier.FREE)
def validate_devanagari_unicode(document: ExamDocument, rule: Rule) -> list[Issue]:
    """Verify that all Hindi/Devanagari text blocks are in canonical Unicode NFC form."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if rule.severity.value == "blocker" else IssueSeverity.WARNING

    for block in document.blocks:
        if block.status == BlockStatus.DROPPED or block.lang.value != "hi":
            continue

        normalized = unicodedata.normalize("NFC", block.text)
        if block.text != normalized:
            issues.append(
                Issue(
                    id=f"r09_nfc_violation_{block.id}",
                    stage="s8_verify",
                    rule=rule.check,
                    page=block.page,
                    element_id=block.id,
                    severity=severity,
                    message=f"Rule R09 violation on page {block.page}: Hindi text block {block.id} is not in Unicode NFC form",
                )
            )

    return issues
