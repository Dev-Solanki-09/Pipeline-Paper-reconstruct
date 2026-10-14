"""Validator for R11: text_layer_agreement.

Verifies that extracted text accurately aligns with the underlying digital PDF text layer
using token-level overlap.
"""

from __future__ import annotations

import re
from typing import Any

from examforge.eval.metrics import normalize_text
from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, TextNode
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator


@register_validator("text_layer_agreement", cost_tier=CostTier.IO)
def validate_text_layer_agreement(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """Check that extracted question text aligns with the PDF text layer."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if (rule and rule.severity.value == "blocker") else IssueSeverity.WARNING
    threshold = (rule.params.get("min_agreement", 0.70) if rule and rule.params else 0.70)

    # Map pages that have valid text layers
    text_layer_pages = {
        p.page_number: p
        for p in document.pages
        if p.has_text_layer and p.text_layer_valid
    }

    if not text_layer_pages:
        return issues

    # Assemble raw text layer tokens per page from trusted layout blocks
    page_text_tokens: dict[int, set[str]] = {}
    for b in document.blocks:
        if b.page in text_layer_pages and b.text:
            clean = normalize_text(b.text)
            tokens = set(clean.split())
            page_text_tokens.setdefault(b.page, set()).update(tokens)

    for q in document.questions:
        q_pages = [p for p in q.source_pages if p in text_layer_pages]
        if not q_pages:
            continue

        # Collect expected tokens in question stem
        stem_parts = []
        if q.stem:
            for n in q.stem:
                if isinstance(n, TextNode) and "en" in n.texts:
                    stem_parts.append(n.texts["en"])
        elif q.stem_text_en:
            stem_parts.append(q.stem_text_en)

        stem_text = normalize_text(" ".join(stem_parts))
        q_tokens = [t for t in stem_text.split() if len(t) > 2]
        if len(q_tokens) < 5:
            continue

        # Combine text layer tokens of the question's source pages
        available_tokens: set[str] = set()
        for p_num in q_pages:
            available_tokens.update(page_text_tokens.get(p_num, set()))

        if not available_tokens:
            continue

        matched_count = sum(1 for t in q_tokens if t in available_tokens)
        agreement = matched_count / len(q_tokens)

        if agreement < threshold:
            issues.append(
                Issue(
                    id=f"r11_disagreement_q{q.number}",
                    stage="s8_verify",
                    question_id=q.id,
                    rule="text_layer_agreement",
                    severity=severity,
                    message=(
                        f"Rule R11 violation: Question Q{q.number} text-layer agreement "
                        f"({agreement:.2f}) below threshold ({threshold:.2f})"
                    ),
                    evidence={
                        "agreement": round(agreement, 3),
                        "threshold": threshold,
                        "matched_tokens": matched_count,
                        "total_tokens": len(q_tokens),
                    },
                )
            )

    return issues
