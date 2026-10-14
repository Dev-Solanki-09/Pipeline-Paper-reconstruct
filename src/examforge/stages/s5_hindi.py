"""
S5b Hindi: Hindi Text Processing & Bilingual Separation.

Normalizes Devanagari Unicode:
1. NFC normalization (combining decomposed matras and nuktas).
2. ASCII pipe to Devanagari danda (| -> । and || -> ॥).
3. Spurious ZWJ/ZWNJ cleanup at word boundaries.
4. Bilingual separation: extracts Hindi text from mixed question stems/options
   into stem_text_hi / text_str_hi to support clean 50/50 dual-column layout.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

from examforge.ir.schema import (
    Block,
    BlockStatus,
    ExamDocument,
    Issue,
    Lang,
    Question,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Devanagari Unicode ranges (U+0900 to U+097F)
_DEVANAGARI_CHAR_RE = re.compile(r"[\u0900-\u097F]")


def contains_devanagari(text: str) -> bool:
    """Check if text contains any Devanagari characters."""
    return bool(_DEVANAGARI_CHAR_RE.search(text)) if text else False


def normalize_hindi_text(text: str) -> str:
    """Normalize Devanagari text with NFC, danda conversion, and ZWJ cleanup."""
    if not text:
        return text

    # 1. Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)

    # 2. Danda normalization (ASCII | preceded by Devanagari)
    # Double pipe || -> double danda ॥ (\u0965)
    text = re.sub(r"([\u0900-\u097F]\s*)\|\|", r"\1॥", text)
    # Single pipe | -> danda । (\u0964)
    text = re.sub(r"([\u0900-\u097F]\s*)\|(?![\w|])", r"\1।", text)

    # 3. Clean spurious ZWJ / ZWNJ at whitespace or boundaries
    text = re.sub(r"(?<=\s)[\u200C\u200D]+", "", text)
    text = re.sub(r"[\u200C\u200D]+(?=\s|$)", "", text)

    return text.strip()


def split_bilingual_text(text: str) -> tuple[str, str]:
    """
    Split mixed bilingual text into (english_text, hindi_text).

    Handles:
    - Line-by-line bilingual text (interleaved or grouped EN lines and HI lines)
    - Slash-delimited bilingual text (per-line or overall: "EN text / HI text")
    - Sentence-level boundaries on the same line (English text followed by Devanagari)
    """
    if not text or not contains_devanagari(text):
        return text, ""

    def is_devanagari_line(s: str) -> bool:
        dev_chars = len(_DEVANAGARI_CHAR_RE.findall(s))
        letter_chars = len(re.findall(r"[\w]", s))
        if letter_chars == 0:
            return dev_chars > 0
        return (dev_chars / letter_chars) > 0.25

    raw_lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # Fast path: single line with slash delimiter "EN option / HI option"
    if len(raw_lines) == 1:
        slash_match = re.search(r"^(.*?)\s+/\s+([0-9\s]*[\u0900-\u097F].*)$", raw_lines[0])
        if slash_match:
            part1 = slash_match.group(1).strip()
            part2 = slash_match.group(2).strip()
            if not contains_devanagari(part1) and contains_devanagari(part2):
                return part1, part2
            elif contains_devanagari(part1) and not contains_devanagari(part2):
                return part2, part1

    en_lines: list[str] = []
    hi_lines: list[str] = []

    for line in raw_lines:
        if not contains_devanagari(line):
            en_lines.append(line)
            continue

        # Line contains Devanagari. Check for slash delimiter within this line:
        slash_m = re.search(r"^(.*?)\s+/\s+(.*[\u0900-\u097F].*)$", line)
        if slash_m:
            p1, p2 = slash_m.group(1).strip(), slash_m.group(2).strip()
            if not contains_devanagari(p1):
                if p1:
                    en_lines.append(p1)
                if p2:
                    hi_lines.append(p2)
                continue

        # Purely / predominantly Devanagari line
        if is_devanagari_line(line) and not re.search(r"[A-Za-z]{3,}", line):
            hi_lines.append(line)
            continue

        # Mixed English and Devanagari on the same line (e.g. "Calculate work done. किए गए कार्य की गणना कीजिए।")
        mixed_m = re.search(r"^([A-Za-z0-9\s.,;:=+*/()\\_\-—–%]+?[.?:]\s*)([\u0900-\u097F].*)$", line)
        if mixed_m:
            en_sub = mixed_m.group(1).strip()
            hi_sub = mixed_m.group(2).strip()
            if en_sub and not contains_devanagari(en_sub):
                en_lines.append(en_sub)
                hi_lines.append(hi_sub)
                continue

        # Fallback for line: classify by predominant character set
        if is_devanagari_line(line):
            hi_lines.append(line)
        else:
            en_lines.append(line)

    if en_lines and hi_lines:
        return "\n".join(en_lines).strip(), "\n".join(hi_lines).strip()
    elif hi_lines and not en_lines:
        return "", "\n".join(hi_lines).strip()
    else:
        # Check overall Devanagari ratio
        dev_count = len(_DEVANAGARI_CHAR_RE.findall(text))
        if dev_count > len(text) * 0.3:
            return "", text.strip()
        return "\n".join(en_lines).strip(), ""


class S5Hindi(Stage):
    """
    Stage 5b: Hindi text processing and bilingual column separation.
    """

    name = "s5_hindi"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["hindi_normalizer", "devanagari_clean"]

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S5b requires blocks to be present in the document."""
        violations = []
        if not ctx.document.blocks:
            violations.append("No blocks found in document — S3 Parse must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict = {}

        use_v2 = bool(ctx.config and ctx.config.flag("lang_v2", default=False))

        # If profile does not include Hindi/Devanagari, pass through cleanly unless v2 with other non-latin scripts
        if ctx.resolved_profile:
            has_hindi = any(
                lang.code == "hi" or lang.script == "Deva"
                for lang in ctx.resolved_profile.languages
            )
            has_non_latin = any(
                lang.script != "Latn"
                for lang in ctx.resolved_profile.languages
            )
            if not has_hindi and not (use_v2 and has_non_latin):
                logger.info("  S5 Hindi: Profile does not include Hindi/Devanagari; skipping.")
                return StageResult(document=doc, metrics={"skipped": True}, issues=issues)

        hindi_blocks_count = 0
        bilingual_split_count = 0

        if use_v2:
            from examforge.lang.bilingual import split_bilingual_by_script
            from examforge.lang.fontmaps import convert_legacy_font, detect_legacy_font, needs_ocr_for_script
            from examforge.lang.registry import detect_lang, get_plugin

            # 1. Process blocks with v2 plugins & font repair
            for b in doc.blocks:
                if b.status == BlockStatus.DROPPED:
                    continue

                # Check legacy font conversion
                f_id, conf = detect_legacy_font(b.text)
                if f_id and conf >= 0.5:
                    if needs_ocr_for_script(b.text):
                        issues.append(
                            Issue(
                                stage="s5_hindi",
                                rule_id="R_FONT",
                                severity=IssueSeverity.WARNING,
                                message=f"Block {b.id} requires OCR fallback due to unmapped legacy font glyphs",
                            )
                        )
                    b.text = convert_legacy_font(b.text, f_id)
                    hindi_blocks_count += 1

                l_code = detect_lang(b.text)
                if l_code == "hi" or contains_devanagari(b.text):
                    norm = get_plugin("hi").normalize(b.text)
                    if norm != b.text:
                        b.text = norm
                        hindi_blocks_count += 1
                    b.lang = Lang.HI
                elif l_code != "en":
                    norm = get_plugin(l_code).normalize(b.text)
                    b.text = norm

            # 2. Process questions with v2 script splitter
            for q in doc.questions:
                # Handle bilingual split for question stems
                if q.stem_text_en and not q.stem_text_hi and contains_devanagari(q.stem_text_en):
                    en_part, hi_part = split_bilingual_by_script(q.stem_text_en, primary_lang="en", secondary_lang="hi")
                    if hi_part:
                        q.stem_text_en = get_plugin("en").normalize(en_part)
                        q.stem_text_hi = get_plugin("hi").normalize(hi_part)
                        bilingual_split_count += 1

                if q.stem_text_hi:
                    q.stem_text_hi = get_plugin("hi").normalize(q.stem_text_hi)

                # Handle bilingual split for options
                for opt in q.options:
                    if opt.text_str_en and not opt.text_str_hi and contains_devanagari(opt.text_str_en):
                        en_part, hi_part = split_bilingual_by_script(opt.text_str_en, primary_lang="en", secondary_lang="hi")
                        if hi_part:
                            opt.text_str_en = get_plugin("en").normalize(en_part)
                            opt.text_str_hi = get_plugin("hi").normalize(hi_part)
                            bilingual_split_count += 1

                    if opt.text_str_hi:
                        opt.text_str_hi = get_plugin("hi").normalize(opt.text_str_hi)

        else:
            # v1 legacy fallback
            # 1. Process blocks
            for b in doc.blocks:
                if b.status == BlockStatus.DROPPED:
                    continue

                if contains_devanagari(b.text):
                    norm = normalize_hindi_text(b.text)
                    if norm != b.text:
                        b.text = norm
                        hindi_blocks_count += 1
                    b.lang = Lang.HI

            # 2. Process questions
            for q in doc.questions:
                # Handle bilingual split for question stems
                if q.stem_text_en and not q.stem_text_hi and contains_devanagari(q.stem_text_en):
                    en_part, hi_part = split_bilingual_text(q.stem_text_en)
                    if hi_part:
                        q.stem_text_en = en_part.strip()
                        q.stem_text_hi = normalize_hindi_text(hi_part)
                        bilingual_split_count += 1

                if q.stem_text_hi:
                    q.stem_text_hi = normalize_hindi_text(q.stem_text_hi)

                # Handle bilingual split for options
                for opt in q.options:
                    if opt.text_str_en and not opt.text_str_hi and contains_devanagari(opt.text_str_en):
                        en_part, hi_part = split_bilingual_text(opt.text_str_en)
                        if hi_part:
                            opt.text_str_en = en_part.strip()
                            opt.text_str_hi = normalize_hindi_text(hi_part)
                            bilingual_split_count += 1

                    if opt.text_str_hi:
                        opt.text_str_hi = normalize_hindi_text(opt.text_str_hi)

        metrics["hindi_blocks_count"] = hindi_blocks_count
        metrics["bilingual_split_count"] = bilingual_split_count

        logger.info(
            "  S5 Hindi complete: normalized %d Hindi blocks, separated %d bilingual question parts (v2=%s)",
            hindi_blocks_count,
            bilingual_split_count,
            use_v2,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Postcondition: check that Hindi text has no raw pipe dandas."""
        violations = []
        for q in result.document.questions:
            if q.stem_text_hi and re.search(r"[\u0900-\u097F]\s*\|(?![\w|])", q.stem_text_hi):
                violations.append(f"Question {q.id} Hindi stem contains unconverted pipe danda: {q.stem_text_hi[:30]}")
        return violations
