"""
Consolidated Validator: furniture_branding (Phase O4.2).

Merges R01 (furniture/headers/footers/page numbers) and R02 (promotional branding/urls/logos)
into a single high-efficiency pass over document blocks.
CostTier: FREE.
"""

from __future__ import annotations

import re

from examforge.ir.schema import (
    BlockStatus,
    BlockType,
    ExamDocument,
    Issue,
    IssueSeverity,
)
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

_PAGE_NUM_RE = re.compile(r"^\s*(?:page\s*)?\d+\s*(?:/\s*\d+|of\s*\d+)?\s*$", re.IGNORECASE)
_ROUGH_WORK_RE = re.compile(r"^\s*space for rough work\s*$", re.IGNORECASE)
_FURNITURE_HEADER_RE = re.compile(
    r"\b(?:confidential|test booklet|exam paper|question paper|candidate's name|roll no)\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b")
_BRAND_KEYWORDS = [
    "allen career institute",
    "resonance eduventures",
    "fiitjee ltd",
    "aakash institute",
    "sankalp batch",
]


@register_validator(
    "furniture_branding",
    cost_tier=CostTier.FREE,
    aliases=["no_headers_footers_page_numbers", "no_brand_text_or_logo"],
)
def validate_furniture_branding(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """
    Consolidated scan for undropped furniture (page numbers, headers, footers)
    and promotional branding (URLs, phones, coaching brand names).
    """
    issues: list[Issue] = []
    severity = (
        IssueSeverity.BLOCKER
        if (rule and getattr(rule.severity, "value", str(rule.severity)) == "blocker")
        else IssueSeverity.WARNING
    )
    rule_name = rule.check if rule and rule.check else "furniture_branding"

    run_furniture = rule_name in ("furniture_branding", "no_headers_footers_page_numbers")
    run_branding = rule_name in ("furniture_branding", "no_brand_text_or_logo")

    for block in document.blocks:
        if block.status == BlockStatus.DROPPED:
            continue

        text = block.text.strip()
        lower = text.lower()

        # 1. Check Furniture (R01 portion)
        if run_furniture:
            is_furniture = False
            furniture_reason = ""

            if block.type in (BlockType.FOOTER, BlockType.PAGE_NUMBER):
                is_furniture = True
                furniture_reason = f"{block.type.value.capitalize()} block is not dropped"
            elif block.type == BlockType.HEADER and _FURNITURE_HEADER_RE.search(text):
                is_furniture = True
                furniture_reason = f"Furniture header '{text}' is not dropped"
            elif _PAGE_NUM_RE.match(text) and len(text) < 15:
                is_furniture = True
                furniture_reason = f"Page number pattern '{text}' not dropped"
            elif _ROUGH_WORK_RE.match(text):
                is_furniture = True
                furniture_reason = "Rough work header not dropped"

            if is_furniture:
                issues.append(
                    Issue(
                        id=f"r01_furniture_{block.id}",
                        stage="s8_verify",
                        rule="no_headers_footers_page_numbers" if rule_name == "no_headers_footers_page_numbers" else "furniture_branding",
                        page=block.page,
                        element_id=block.id,
                        severity=severity,
                        message=f"Rule R01 violation: {furniture_reason}",
                        evidence={"text": text, "type": block.type.value},
                    )
                )

        # 2. Check Branding (R02 portion)
        if run_branding:
            has_brand = False
            brand_match = ""

            if block.type in (BlockType.LOGO, BlockType.QR_CODE, BlockType.URL):
                has_brand = True
                brand_match = f"{block.type.value.capitalize()} block"
            elif _URL_RE.search(text):
                has_brand = True
                brand_match = "Promotional URL"
            elif _PHONE_RE.search(text):
                has_brand = True
                brand_match = "Contact Phone Number"
            else:
                for kw in _BRAND_KEYWORDS:
                    if kw in lower:
                        has_brand = True
                        brand_match = kw
                        break

            if has_brand:
                issues.append(
                    Issue(
                        id=f"r02_brand_{block.id}",
                        stage="s8_verify",
                        rule="no_brand_text_or_logo" if rule_name == "no_brand_text_or_logo" else "furniture_branding",
                        page=block.page,
                        element_id=block.id,
                        severity=severity,
                        message=f"Rule R02 violation: Found branding/promotional content ({brand_match})",
                        evidence={"text": text, "match": brand_match},
                    )
                )

    return issues
