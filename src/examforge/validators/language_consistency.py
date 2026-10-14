"""
Consolidated Validator: language_consistency (Phase O4.2).

Merges R05 (bilingual stem pair completeness) and R10 (bilingual invariant tokens & options consistency)
into a unified bilingual verification pass.
CostTier: FREE.
"""

from __future__ import annotations

import collections
import re
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, Question, TextNode
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

# Devanagari to Western digit translation table
DEVA_TO_WESTERN = str.maketrans("०१२३४५६७८९", "0123456789")

# Match numbers (integers and decimals)
NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

# Match Latin symbols and units (e.g., kg, m/s, DNA, ATP, K2Cr2O7)
LATIN_TOKEN_RE = re.compile(r"\b[A-Za-z]+[0-9A-Za-z_/-]*\b")


_SCIENTIFIC_UNITS = {
    "kg", "g", "mg", "m/s", "m/s^2", "m", "cm", "mm", "nm", "km",
    "N", "J", "W", "Pa", "mol", "K", "V", "A", "Hz", "pF", "uF", "μF", "µF",
    "mV", "kV", "mA", "kA", "rad", "deg", "cal", "kcal", "eV", "MeV", "GeV", "s", "h", "min"
}


def extract_invariant_tokens(text: str) -> dict[str, list[str]]:
    """Extract numbers and Latin scientific/unit tokens from text."""
    canon_text = text.translate(DEVA_TO_WESTERN)
    numbers = NUM_RE.findall(canon_text)

    # Invariant Latin tokens in bilingual exams are scientific units, chemical formulas,
    # or uppercase acronyms — regular prose words are translated to Hindi and not invariant.
    raw_latin = LATIN_TOKEN_RE.findall(canon_text)
    latin_tokens = []
    for t in raw_latin:
        if t in _SCIENTIFIC_UNITS:
            latin_tokens.append(t)
        elif re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", t):
            latin_tokens.append(t)
        elif t.isupper() and len(t) >= 2:
            latin_tokens.append(t)
        elif t in ("V", "T", "R", "W", "P", "F", "K", "I", "C", "N", "O", "S", "g", "m", "s"):
            latin_tokens.append(t)

    return {
        "numbers": sorted(numbers),
        "latin": sorted(latin_tokens),
    }


def _get_bilingual_stem_texts(question: Question) -> tuple[str, str]:
    """Retrieve English and Hindi stem texts."""
    en_parts: list[str] = []
    hi_parts: list[str] = []

    if question.stem:
        for node in question.stem:
            if isinstance(node, TextNode):
                if "en" in node.texts:
                    en_parts.append(node.texts["en"])
                if "hi" in node.texts:
                    hi_parts.append(node.texts["hi"])

    en_text = " ".join(en_parts).strip() or question.stem_text_en
    hi_text = " ".join(hi_parts).strip() or getattr(question, "stem_text_hi", "")
    return en_text, hi_text


@register_validator(
    "language_consistency",
    cost_tier=CostTier.FREE,
    aliases=["en_hi_pairs_complete"],
)
def validate_language_consistency(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """
    Consolidated verification of bilingual pair completeness (R05)
    and cross-language invariant consistency (R10).
    """
    issues: list[Issue] = []
    severity = (
        IssueSeverity.BLOCKER
        if (rule and getattr(rule.severity, "value", str(rule.severity)) == "blocker")
        else IssueSeverity.WARNING
    )
    rule_name = rule.check if rule and rule.check else "language_consistency"

    # Check if document has any bilingual content
    has_hindi_blocks = any(b.lang.value == "hi" for b in document.blocks)
    has_hindi_questions = any(bool(q.stem_text_hi) for q in document.questions)
    is_bilingual_doc = has_hindi_blocks or has_hindi_questions

    if not is_bilingual_doc:
        # Monolingual document: rule passes cleanly
        return issues

    for q in document.questions:
        en_stem, hi_stem = _get_bilingual_stem_texts(q)

        # 1. R05 Check: Completeness of English & Hindi pairs
        has_en = bool(en_stem.strip())
        has_hi = bool(hi_stem.strip())

        if has_en != has_hi:
            missing_lang = "Hindi" if not has_hi else "English"
            issues.append(
                Issue(
                    id=f"r05_missing_lang_{q.id}",
                    stage="s8_verify",
                    rule="en_hi_pairs_complete" if rule_name == "en_hi_pairs_complete" else "language_consistency",
                    question_id=q.id,
                    element_id=q.id,
                    severity=severity,
                    message=f"Rule R05 violation: Question {q.number} is missing {missing_lang} stem in bilingual exam",
                )
            )
            # Cannot do token consistency if one language is missing
            continue

        if not has_en and not has_hi:
            continue

        if rule_name == "en_hi_pairs_complete":
            continue

        # 2. R10 Check: Invariant tokens cross-verification
        en_tokens = extract_invariant_tokens(en_stem)
        hi_tokens = extract_invariant_tokens(hi_stem)

        # 2a. Number multiset matching
        en_nums = collections.Counter(en_tokens["numbers"])
        hi_nums = collections.Counter(hi_tokens["numbers"])
        if en_nums != hi_nums:
            diff_en = list((en_nums - hi_nums).elements())
            diff_hi = list((hi_nums - en_nums).elements())
            issues.append(
                Issue(
                    id=f"r10_nums_{q.id}",
                    stage="s8_verify",
                    rule="language_consistency",
                    question_id=q.id,
                    severity=severity,
                    message=f"Rule R10 violation: Number mismatch between EN and HI stems in Question {q.number}",
                    evidence={"en_excess": diff_en, "hi_excess": diff_hi},
                )
            )

        # 2b. Latin units & chemical formula preservation
        en_latin = collections.Counter(en_tokens["latin"])
        hi_latin = collections.Counter(hi_tokens["latin"])
        diff_latin_en = list((en_latin - hi_latin).elements())
        if diff_latin_en:
            issues.append(
                Issue(
                    id=f"r10_latin_{q.id}",
                    stage="s8_verify",
                    rule="language_consistency",
                    question_id=q.id,
                    severity=IssueSeverity.WARNING,
                    message=f"Rule R10 warning: Latin symbols/units in EN missing from HI in Question {q.number}",
                    evidence={"missing_in_hi": diff_latin_en},
                )
            )

        # 2c. Option count & bilingual structure matching
        en_opts = [opt for opt in q.options if opt.text_str_en.strip()]
        hi_opts = [opt for opt in q.options if opt.text_str_hi.strip()]
        if len(en_opts) > 0 and len(hi_opts) > 0 and len(en_opts) != len(hi_opts):
            issues.append(
                Issue(
                    id=f"r10_opt_count_{q.id}",
                    stage="s8_verify",
                    rule="language_consistency",
                    question_id=q.id,
                    severity=severity,
                    message=f"Rule R10 violation: Option count mismatch (EN={len(en_opts)}, HI={len(hi_opts)}) in Question {q.number}",
                    evidence={"en_count": len(en_opts), "hi_count": len(hi_opts)},
                )
            )

        # 2d. Sane length ratio
        len_en = len(en_stem)
        len_hi = len(hi_stem)
        if len_en > 20 and len_hi > 20:
            ratio = len_en / len_hi
            if ratio < 0.25 or ratio > 4.0:
                issues.append(
                    Issue(
                        id=f"r10_ratio_{q.id}",
                        stage="s8_verify",
                        rule="language_consistency",
                        question_id=q.id,
                        severity=IssueSeverity.WARNING,
                        message=f"Rule R10 warning: Extreme length ratio ({ratio:.2f}) between EN and HI in Question {q.number}",
                        evidence={"en_len": len_en, "hi_len": len_hi, "ratio": ratio},
                    )
                )

    return issues
