"""
Bilingual and N-language text segmentation based on Unicode scripts.

Supports:
- English + Devanagari (Hindi, Marathi)
- English + Indic scripts (Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Odia)
- English + Urdu / Arabic
- Multi-lingual (3+ languages) question papers
"""

from __future__ import annotations

import re

from examforge.lang.registry import detect_lang, detect_script, get_plugin

# Regex to detect any non-Latin scripts (Indic, Arabic, CJK)
_NON_LATIN_RE = re.compile(
    r"[\u0900-\u0D7F\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u4E00-\u9FFF]"
)


def contains_non_latin(text: str) -> bool:
    """Check if text contains any non-Latin Unicode characters."""
    return bool(_NON_LATIN_RE.search(text)) if text else False


def split_bilingual_by_script(
    text: str,
    primary_lang: str = "en",
    secondary_lang: str = "hi",
) -> tuple[str, str]:
    """
    Split mixed bilingual text into (primary_text, secondary_text).

    Handles:
    - Slash-delimited options/sentences: "10 m/s / 10 मी/से"
    - Interleaved/grouped multi-line text
    - Same-line sentence boundary
    """
    if not text or not contains_non_latin(text):
        return text, ""

    sec_plugin = get_plugin(secondary_lang)

    # 1. Fast-path: single line with slash delimiter
    raw_lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(raw_lines) == 1:
        slash_match = re.search(r"^(.*?)\s+/\s+(.*)$", raw_lines[0])
        if slash_match:
            part1 = slash_match.group(1).strip()
            part2 = slash_match.group(2).strip()
            lang1 = detect_lang(part1)
            lang2 = detect_lang(part2)
            if lang1 == primary_lang and lang2 == secondary_lang:
                return part1, part2
            elif lang1 == secondary_lang and lang2 == primary_lang:
                return part2, part1

    pri_lines: list[str] = []
    sec_lines: list[str] = []

    for line in raw_lines:
        if not contains_non_latin(line):
            pri_lines.append(line)
            continue

        # Check for inline slash separator in this line
        slash_m = re.search(r"^(.*?)\s+/\s+(.*)$", line)
        if slash_m:
            p1, p2 = slash_m.group(1).strip(), slash_m.group(2).strip()
            if not contains_non_latin(p1) and contains_non_latin(p2):
                if p1:
                    pri_lines.append(p1)
                if p2:
                    sec_lines.append(p2)
                continue

        # Check for inline sentence boundary on the same line
        # e.g. "Calculate work. कार्य की गणना करें।"
        mixed_m = re.search(
            r"^([A-Za-z0-9\s.,;:=+*/()\\_\-—–%\"'?!]+?[.?!:]\s*)([^\x00-\x7F].*)$",
            line,
        )
        if mixed_m:
            p1 = mixed_m.group(1).strip()
            p2 = mixed_m.group(2).strip()
            if p1 and not contains_non_latin(p1) and contains_non_latin(p2):
                pri_lines.append(p1)
                sec_lines.append(p2)
                continue

        # Determine dominant script for the line
        line_lang = detect_lang(line)
        if line_lang == secondary_lang:
            sec_lines.append(line)
        else:
            pri_lines.append(line)

    pri_res = "\n".join(pri_lines).strip()
    sec_res = "\n".join(sec_lines).strip()

    if pri_res and sec_res:
        return pri_res, sec_res
    elif sec_res and not pri_res:
        return "", sec_res
    else:
        return pri_res, ""


def segment_multilingual_text(
    text: str,
    target_languages: list[str] | None = None,
) -> dict[str, str]:
    """
    Segment text into a dictionary of {lang_code: text} for N languages.
    """
    if not text:
        return {}

    targets = [l.lower() for l in (target_languages or ["en", "hi"])]
    results: dict[str, list[str]] = {t: [] for t in targets}

    # Check for slash-delimited representation across N languages
    # e.g., "Part EN / Part HI / Part BN"
    raw_lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(raw_lines) == 1 and " / " in raw_lines[0]:
        parts = [p.strip() for p in raw_lines[0].split(" / ")]
        if len(parts) >= 2:
            assigned: dict[str, str] = {}
            for part in parts:
                p_lang = detect_lang(part)
                if p_lang in targets and p_lang not in assigned:
                    assigned[p_lang] = part
                else:
                    # Find first unassigned target
                    for t in targets:
                        if t not in assigned:
                            assigned[t] = part
                            break
            return assigned

    # Line-by-line classification
    for line in raw_lines:
        # Check inline slash
        if " / " in line:
            parts = [p.strip() for p in line.split(" / ")]
            if len(parts) == len(targets):
                for p, t in zip(parts, targets):
                    results[t].append(p)
                continue

        l_lang = detect_lang(line)
        if l_lang in results:
            results[l_lang].append(line)
        else:
            # Fallback to primary language
            results[targets[0]].append(line)

    return {t: "\n".join(lines).strip() for t, lines in results.items() if lines}
