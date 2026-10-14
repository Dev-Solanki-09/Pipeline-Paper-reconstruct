"""
Stage S5 Normalize: Unified Mathematical & Linguistic Normalization (Phase O3.4).

Consolidates S5 Math and S5 Hindi into a single high-efficiency pass that:
1. Walks each Question exactly once.
2. Performs Unicode-to-LaTeX math formatting and KaTeX delimiter wrapping.
3. Performs Devanagari NFC normalization, danda conversion, and bilingual splitting.
4. Enforces O3.6 Do-No-Harm invariant: multiset of digits and scientific units
   is strictly preserved across all transformations.
"""

from __future__ import annotations

from collections import Counter
import logging
import re
import unicodedata
from typing import Any

from examforge.ir.schema import (
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    Issue,
    IssueSeverity,
    Lang,
    Question,
)
from examforge.eval.metrics import levenshtein_distance
from examforge.lang.boilerplate import snap_to_canonical_boilerplate
from examforge.lang.registry import get_plugin
from examforge.stages.base import Stage, StageContext, StageResult
from examforge.stages.s5_math import (
    _LATEX_COMMAND_RE,
    check_balanced_delimiters,
    convert_unicode_math,
    format_math,
    format_math_v2,
    wrap_math_delimiters,
)
from examforge.lang.bilingual import split_bilingual_by_script
from examforge.stages.s5_hindi import (
    contains_devanagari,
    normalize_hindi_text,
    split_bilingual_text,
)

logger = logging.getLogger(__name__)

# Pattern for extracting digits for multiset preservation
_DIGIT_RE = re.compile(r"\d")
_UNIT_RE = re.compile(
    r"\b(?:kg|m/s|m/s\^2|N|J|W|Pa|mol|K|V|A|Hz|cm|mm|nm|km|pF|μF|µF|mV|kV|mA|kA)\b"
)


def _extract_digits(text: str) -> Counter[str]:
    """Extract multiset of digits from text."""
    if not text:
        return Counter()
    return Counter(_DIGIT_RE.findall(text))


def _extract_units(text: str) -> Counter[str]:
    """Extract multiset of scientific units from text."""
    if not text:
        return Counter()
    return Counter(_UNIT_RE.findall(text))


class S5Normalize(Stage):
    """
    Stage 5: Unified Math, Chemistry & Language Normalization pass.
    """

    name = "s5_normalize"

    @classmethod
    def capabilities(cls) -> list[str]:
        return [
            "math_latex",
            "formula_wrap",
            "devanagari_normalize",
            "bilingual_split",
            "stem_lexicon",
        ]

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S5 requires blocks or questions to be present."""
        violations = []
        if not ctx.document.blocks and not ctx.document.questions:
            violations.append("No blocks or questions found — S3/S4 must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict[str, Any] = {}

        use_v2 = bool(
            (ctx.config and ctx.config.flag("lang_v2", default=True))
            or (ctx.resolved_profile and getattr(ctx.resolved_profile, "flags", {}).get("lang_v2", True))
        )

        edit_budget_threshold = float(
            getattr(ctx.config, "edit_budget_threshold", 0.35) if ctx.config else 0.35
        )

        formulas_converted = 0
        hindi_blocks_count = 0
        bilingual_split_count = 0
        do_no_harm_verified = 0
        do_no_harm_violations = 0
        edit_budget_violations = 0
        boilerplate_snaps = 0

        def _normalize_math_text(txt: str) -> str:
            nonlocal formulas_converted
            if not txt:
                return txt
            if use_v2:
                formatted, new_issues = format_math_v2(txt)
                issues.extend(new_issues)
            else:
                formatted = format_math(txt)

            if formatted != txt:
                formulas_converted += 1
            return formatted

        def _normalize_hindi_str(txt: str) -> str:
            nonlocal hindi_blocks_count
            if not txt or not contains_devanagari(txt):
                return txt
            if use_v2:
                norm = get_plugin("hi").normalize(txt)
            else:
                norm = normalize_hindi_text(txt)
            if norm != txt:
                hindi_blocks_count += 1
            return norm

        # 1. Process standalone blocks (if present)
        for b in doc.blocks:
            if b.status == BlockStatus.DROPPED:
                continue

            orig_text = b.text
            digits_before = _extract_digits(orig_text)
            units_before = _extract_units(orig_text)

            # Language / Hindi normalization
            processed_text = orig_text
            if contains_devanagari(processed_text):
                processed_text = _normalize_hindi_str(processed_text)
                b.lang = Lang.HI

            # Math normalization
            processed_text = _normalize_math_text(processed_text)

            # O3.6 / O7.3 Do-no-harm digit & unit check
            digits_after = _extract_digits(processed_text)
            units_after = _extract_units(processed_text)
            if digits_before != digits_after:
                do_no_harm_violations += 1
                issues.append(
                    Issue(
                        id=f"do_no_harm_block_{b.id}",
                        stage=self.name,
                        severity=IssueSeverity.WARNING,
                        message=f"Digit multiset altered in block {b.id}: {dict(digits_before)} -> {dict(digits_after)}. Reverted.",
                    )
                )
                processed_text = orig_text
            elif units_before != units_after:
                do_no_harm_violations += 1
                issues.append(
                    Issue(
                        id=f"do_no_harm_unit_block_{b.id}",
                        stage=self.name,
                        severity=IssueSeverity.WARNING,
                        message=f"Unit multiset altered in block {b.id}: {dict(units_before)} -> {dict(units_after)}. Reverted.",
                    )
                )
                processed_text = orig_text
            else:
                do_no_harm_verified += 1

            if processed_text != orig_text:
                b.text = processed_text
                if _LATEX_COMMAND_RE.search(processed_text) and len(b.text.split()) < 10:
                    b.type = BlockType.FORMULA

        # 2. Process questions in a single unified walk with O7.1 Edit Budget & O7.3 Unit Whitelist
        for q in doc.questions:
            # Capture original state for rollback if edit budget or whitelist violated
            orig_stem_en = q.stem_text_en
            orig_stem_hi = q.stem_text_hi
            orig_opt_en = [opt.text_str_en for opt in q.options]
            orig_opt_hi = [opt.text_str_hi for opt in q.options]
            orig_stem_blocks_en = [b.text for b in q.stem_en]
            orig_stem_blocks_hi = [b.text for b in q.stem_hi]
            orig_opt_blocks_en = [[b.text for b in opt.text_en] for opt in q.options]
            orig_opt_blocks_hi = [[b.text for b in opt.text_hi] for opt in q.options]

            orig_combined = (
                (orig_stem_en or "") + " " + (orig_stem_hi or "") + " "
                + " ".join(orig_opt_en) + " " + " ".join(orig_opt_hi)
            )
            q_digits_before = _extract_digits(orig_combined)
            q_units_before = _extract_units(orig_combined)

            # Boilerplate snapping (Phase O7.4)
            if q.stem_text_en:
                snapped, did_snap = snap_to_canonical_boilerplate(q.stem_text_en)
                if did_snap:
                    q.stem_text_en = snapped
                    boilerplate_snaps += 1
            if q.stem_text_hi:
                snapped, did_snap = snap_to_canonical_boilerplate(q.stem_text_hi)
                if did_snap:
                    q.stem_text_hi = snapped
                    boilerplate_snaps += 1

            # A. Bilingual split on stems if needed
            if q.stem_text_en and not q.stem_text_hi and contains_devanagari(q.stem_text_en):
                if use_v2:
                    en_part, hi_part = split_bilingual_by_script(q.stem_text_en, primary_lang="en", secondary_lang="hi")
                else:
                    en_part, hi_part = split_bilingual_text(q.stem_text_en)
                if hi_part:
                    q.stem_text_en = en_part.strip()
                    q.stem_text_hi = hi_part.strip()
                    bilingual_split_count += 1

            # B. Normalize stems
            if q.stem_text_en:
                q.stem_text_en = _normalize_math_text(q.stem_text_en)
            if q.stem_text_hi:
                q.stem_text_hi = _normalize_hindi_str(q.stem_text_hi)
                q.stem_text_hi = _normalize_math_text(q.stem_text_hi)

            # C. Normalize stem blocks
            for b in q.stem_en:
                b.text = _normalize_math_text(b.text)
            for b in q.stem_hi:
                b.text = _normalize_hindi_str(b.text)
                b.text = _normalize_math_text(b.text)

            # D. Process options
            for opt in q.options:
                if opt.text_str_en and not opt.text_str_hi and contains_devanagari(opt.text_str_en):
                    if use_v2:
                        en_p, hi_p = split_bilingual_by_script(opt.text_str_en, primary_lang="en", secondary_lang="hi")
                    else:
                        en_p, hi_p = split_bilingual_text(opt.text_str_en)
                    if hi_p:
                        opt.text_str_en = en_p.strip()
                        opt.text_str_hi = hi_p.strip()
                        bilingual_split_count += 1

                if opt.text_str_en:
                    opt.text_str_en = _normalize_math_text(opt.text_str_en)
                if opt.text_str_hi:
                    opt.text_str_hi = _normalize_hindi_str(opt.text_str_hi)
                    opt.text_str_hi = _normalize_math_text(opt.text_str_hi)

                for b in opt.text_en:
                    b.text = _normalize_math_text(b.text)
                for b in opt.text_hi:
                    b.text = _normalize_hindi_str(b.text)
                    b.text = _normalize_math_text(b.text)

            # E. O7.1 Edit Budget verification
            new_combined = (
                (q.stem_text_en or "") + " " + (q.stem_text_hi or "") + " "
                + " ".join(opt.text_str_en for opt in q.options) + " "
                + " ".join(opt.text_str_hi for opt in q.options)
            )
            edit_dist = levenshtein_distance(orig_combined, new_combined)
            edit_ratio = edit_dist / max(len(orig_combined), 1)

            # Check if fontmap transliteration is intentionally taking place
            has_fontmap = bool(
                ctx.resolved_profile and getattr(ctx.resolved_profile, "font_maps", None)
            )

            rollback_needed = False
            if edit_ratio > edit_budget_threshold and not has_fontmap:
                rollback_needed = True
                edit_budget_violations += 1
                issues.append(
                    Issue(
                        id=f"edit_budget_exceeded_{q.id}",
                        stage=self.name,
                        severity=IssueSeverity.WARNING,
                        message=f"Edit budget exceeded for question {q.id}: edit ratio {edit_ratio:.3f} > {edit_budget_threshold}. Rewriting reverted.",
                    )
                )

            # F. O3.6 / O7.3 Do-no-harm digit & unit verification
            q_digits_after = _extract_digits(new_combined)
            q_units_after = _extract_units(new_combined)

            if q_digits_before != q_digits_after:
                rollback_needed = True
                do_no_harm_violations += 1
                issues.append(
                    Issue(
                        id=f"do_no_harm_q_{q.id}",
                        stage=self.name,
                        severity=IssueSeverity.WARNING,
                        message=f"Digit multiset altered in question {q.id}: {dict(q_digits_before)} -> {dict(q_digits_after)}. Reverted.",
                    )
                )
            elif q_units_before != q_units_after:
                rollback_needed = True
                do_no_harm_violations += 1
                issues.append(
                    Issue(
                        id=f"do_no_harm_units_q_{q.id}",
                        stage=self.name,
                        severity=IssueSeverity.WARNING,
                        message=f"Unit multiset altered in question {q.id}: {dict(q_units_before)} -> {dict(q_units_after)}. Reverted.",
                    )
                )
            else:
                if not rollback_needed:
                    do_no_harm_verified += 1

            # Perform rollback if invariants violated
            if rollback_needed:
                q.stem_text_en = orig_stem_en
                q.stem_text_hi = orig_stem_hi
                for opt, orig_o_en, orig_o_hi in zip(q.options, orig_opt_en, orig_opt_hi):
                    opt.text_str_en = orig_o_en
                    opt.text_str_hi = orig_o_hi
                for b, orig_t in zip(q.stem_en, orig_stem_blocks_en):
                    b.text = orig_t
                for b, orig_t in zip(q.stem_hi, orig_stem_blocks_hi):
                    b.text = orig_t
                for opt, orig_blocks in zip(q.options, orig_opt_blocks_en):
                    for b, orig_t in zip(opt.text_en, orig_blocks):
                        b.text = orig_t
                for opt, orig_blocks in zip(q.options, orig_opt_blocks_hi):
                    for b, orig_t in zip(opt.text_hi, orig_blocks):
                        b.text = orig_t

        metrics.update({
            "s5_unified_normalized": True,
            "formulas_converted": formulas_converted,
            "hindi_blocks_count": hindi_blocks_count,
            "bilingual_split_count": bilingual_split_count,
            "do_no_harm_verified": do_no_harm_verified,
            "do_no_harm_violations": do_no_harm_violations,
        })

        logger.info(
            "  S5 Normalize complete: %d formulas converted, %d Hindi blocks normalized, %d bilingual splits (Do-no-harm verified=%d)",
            formulas_converted,
            hindi_blocks_count,
            bilingual_split_count,
            do_no_harm_verified,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Verify delimiter balance and no raw pipe dandas."""
        violations = []
        for q in result.document.questions:
            for b in q.stem_en + q.stem_hi:
                if not check_balanced_delimiters(b.text):
                    violations.append(
                        f"Question {q.id} stem block {b.id} has unbalanced math delimiters: {b.text[:40]}"
                    )
            for opt in q.options:
                for b in opt.text_en + opt.text_hi:
                    if not check_balanced_delimiters(b.text):
                        violations.append(
                            f"Question {q.id} option {opt.label} has unbalanced delimiters: {b.text[:40]}"
                        )
            if q.stem_text_hi and re.search(r"[\u0900-\u097F]\s*\|(?![\w|])", q.stem_text_hi):
                violations.append(
                    f"Question {q.id} Hindi stem contains unconverted pipe danda: {q.stem_text_hi[:30]}"
                )
        return violations
