"""Branding scrubber with scientific constants, abbreviations, and chemistry guards."""

from __future__ import annotations

import re
from examforge.ir.schema import Block

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+91[- ]?)?[6-9]\d{9}\b")

# Traps that must never be considered branding: physical constants, units, latin abbreviations, chemistry
_SCIENTIFIC_CONSTANTS_RE = re.compile(
    r"\b(?:[ghckRe]|eps_0|N_A)\s*=\s*[\d.]+(?:\s*[xX*]\s*10\^?[-+]?\d+)?\s*(?:m/s\^?2|m/s|J/(?:mol\s*K)|J\s*s|F/m|N/m|kg|mol)\b|"
    r"\b(?:Planck|gas constant|permittivity|speed of light|acceleration due to gravity)\b",
    re.IGNORECASE,
)
_ABBREVIATIONS_RE = re.compile(
    r"(?:^|[\s(])(?:e\.g\.|i\.e\.|viz\.|etc\.)(?:[\s,;)]|$)",
    re.IGNORECASE,
)
_CHEMISTRY_FORMULA_RE = re.compile(
    r"\b(?:NaCl|AgNO3|H2SO4|HCl|HNO3|NaOH|CaCO3|CO2|H2O|KMnO4|FeSO4)\b",
)


def is_false_positive_trap(text: str) -> bool:
    """Return True if text contains scientific constants, formulas, or standard abbreviations."""
    if _SCIENTIFIC_CONSTANTS_RE.search(text):
        return True
    if _ABBREVIATIONS_RE.search(text):
        return True
    if _CHEMISTRY_FORMULA_RE.search(text):
        return True
    return False


def scrub_branding_blocks(
    blocks: list[Block],
    custom_patterns: list[str] | None = None,
) -> list[str]:
    """Identify blocks containing contact URLs, helpline phones, or coaching branding."""
    branding_ids: list[str] = []

    compiled_custom = []
    if custom_patterns:
        for p in custom_patterns:
            try:
                compiled_custom.append(re.compile(p, re.IGNORECASE))
            except re.error:
                pass

    for b in blocks:
        text = b.text.strip()
        if not text:
            continue

        # False-positive guard
        if is_false_positive_trap(text):
            continue

        # 1. URLs
        if URL_RE.search(text):
            branding_ids.append(b.id)
            continue

        # 2. Standalone phone numbers
        if PHONE_RE.search(text) and len(text) < 45:
            branding_ids.append(b.id)
            continue

        # 3. Profile-specified branding patterns
        if compiled_custom and any(pat.search(text) for pat in compiled_custom):
            # Restrict coaching name matches to headers (<0.15) or footers (>0.85) or short length
            if len(text) < 60 and (not b.bbox_norm or b.bbox_norm[1] < 0.15 or b.bbox_norm[1] > 0.85):
                branding_ids.append(b.id)

    return branding_ids
