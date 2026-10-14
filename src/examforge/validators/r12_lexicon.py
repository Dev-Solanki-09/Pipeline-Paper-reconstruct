"""Validator for R12: lexicon.

Verifies domain vocabulary against physics, chemistry, biology, math, and units lexicons.
Detects potential OCR typos (edit distance <= 2) and attaches correction candidates.
Supports conservative autofix when distance == 1 and unique candidate without digit changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, TextNode
from examforge.spec import Rule
from examforge.validators.registry import register_validator

logger = logging.getLogger(__name__)

# Bounded Levenshtein distance for performance
def bounded_levenshtein(s1: str, s2: str, max_dist: int = 2) -> int:
    """Calculate Levenshtein distance with early-exit if distance > max_dist."""
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > max_dist:
        return max_dist + 1

    # Ensure s1 is shorter or equal length
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    prev_row = list(range(len1 + 1))
    for i, c2 in enumerate(s2, 1):
        curr_row = [i] * (len1 + 1)
        min_val = curr_row[0]
        for j, c1 in enumerate(s1, 1):
            insert_cost = curr_row[j - 1] + 1
            delete_cost = prev_row[j] + 1
            replace_cost = prev_row[j - 1] + (0 if c1 == c2 else 1)
            val = min(insert_cost, delete_cost, replace_cost)
            curr_row[j] = val
            if val < min_val:
                min_val = val
        if min_val > max_dist:
            return max_dist + 1
        prev_row = curr_row

    return prev_row[len1]


_LEXICON_CACHE: dict[int, set[str]] = {}
_ALL_LEXICON_TERMS: set[str] = set()
_COMMON_WORDS: set[str] = set()


def load_domain_lexicons(lexicon_dir: Path | None = None) -> tuple[dict[int, set[str]], set[str], set[str]]:
    """Load and index domain lexicons by word length, plus common vocabulary."""
    global _LEXICON_CACHE, _ALL_LEXICON_TERMS, _COMMON_WORDS
    if _ALL_LEXICON_TERMS:
        return _LEXICON_CACHE, _ALL_LEXICON_TERMS, _COMMON_WORDS

    if lexicon_dir is None:
        lexicon_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "lexicons"

    terms: set[str] = set()
    common: set[str] = set()
    by_len: dict[int, set[str]] = {}

    if lexicon_dir.exists():
        for f in lexicon_dir.glob("*.txt"):
            try:
                is_common = f.name.startswith("common")
                for line in f.read_text(encoding="utf-8").splitlines():
                    word = line.strip().lower()
                    if word and not word.startswith("#"):
                        if is_common:
                            common.add(word)
                        else:
                            terms.add(word)
                            by_len.setdefault(len(word), set()).add(word)
            except Exception as e:
                logger.warning("Could not read lexicon file %s: %e", f, e)

    _LEXICON_CACHE = by_len
    _ALL_LEXICON_TERMS = terms
    _COMMON_WORDS = common
    return _LEXICON_CACHE, _ALL_LEXICON_TERMS, _COMMON_WORDS


WORD_SPLIT_RE = re.compile(r"[^\w\-\./]+")


_SUFFIX_STEMS = [
    ("ly", ""),
    ("ing", ""),
    ("ing", "e"),
    ("ed", ""),
    ("ed", "e"),
    ("es", ""),
    ("s", ""),
    ("d", ""),
    ("ive", "ion"),
    ("ive", "e"),
    ("ive", ""),
]


def _is_known_word(word: str, all_terms: set[str], common_words: set[str]) -> bool:
    if word in all_terms or word in common_words:
        return True
    for suff, repl in _SUFFIX_STEMS:
        if word.endswith(suff) and len(word) > len(suff) + 2:
            stem = word[:-len(suff)] + repl
            if stem in all_terms or stem in common_words:
                return True
    return False


_WORD_CANDIDATE_CACHE: dict[str, list[tuple[int, str]]] = {}


def _get_candidates(
    lower_word: str,
    by_len: dict[int, set[str]],
    all_terms: set[str],
    common_words: set[str],
    max_distance: int = 2,
) -> list[tuple[int, str]]:
    if lower_word in _WORD_CANDIDATE_CACHE:
        return _WORD_CANDIDATE_CACHE[lower_word]

    if _is_known_word(lower_word, all_terms, common_words):
        _WORD_CANDIDATE_CACHE[lower_word] = []
        return []

    word_set = set(lower_word)
    candidates: list[tuple[int, str]] = []

    for cand_len in range(len(lower_word) - max_distance, len(lower_word) + max_distance + 1):
        for term in by_len.get(cand_len, set()):
            term_set = set(term)
            if len(word_set - term_set) > max_distance or len(term_set - word_set) > max_distance:
                continue
            dist = bounded_levenshtein(lower_word, term, max_distance)
            if 0 < dist <= max_distance:
                candidates.append((dist, term))

    candidates.sort()
    _WORD_CANDIDATE_CACHE[lower_word] = candidates
    return candidates


from examforge.validators.base import CostTier


@register_validator("lexicon", cost_tier=CostTier.FREE)
def validate_lexicon(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """Flag extracted words that closely match domain vocabulary with edit distance <= 2."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if (rule and rule.severity.value == "blocker") else IssueSeverity.WARNING
    params = rule.params if rule and rule.params else {}
    autofix = params.get("autofix", False)
    max_distance = params.get("max_distance", 2)

    by_len, all_terms, common_words = load_domain_lexicons()
    if not all_terms:
        return issues

    for q in document.questions:
        # Check text nodes in stem and options
        text_nodes: list[TextNode] = []
        if q.stem:
            for node in q.stem:
                if isinstance(node, TextNode):
                    text_nodes.append(node)
        for opt in q.options:
            for node in opt.content:
                if isinstance(node, TextNode):
                    text_nodes.append(node)

        for node in text_nodes:
            for lang, text in list(node.texts.items()):
                # We only check Latin/English text for domain vocabulary
                if lang != "en":
                    continue

                words = [w.strip(".,;:!?()[]{}'\"") for w in WORD_SPLIT_RE.split(text)]
                modified_text = text

                for word in set(words):
                    # Only test words with 4+ characters, purely alphabetic
                    if len(word) < 4 or not word.isalpha():
                        continue
                    lower_word = word.lower()
                    candidates = _get_candidates(lower_word, by_len, all_terms, common_words, max_distance)
                    if not candidates:
                        continue

                    min_dist = candidates[0][0]
                    best_candidates = [term for d, term in candidates if d == min_dist]

                    # Auto-fix rule: autofix enabled, exactly one candidate, distance == 1, no digits changed
                    fixed = False
                    if autofix and len(best_candidates) == 1 and min_dist == 1:
                        replacement = best_candidates[0]
                        # Preserve case if original was title-case or upper
                        if word.isupper():
                            replacement = replacement.upper()
                        elif word.istitle():
                            replacement = replacement.capitalize()

                        # Replace standalone word in modified_text
                        pattern = r"\b" + re.escape(word) + r"\b"
                        modified_text = re.sub(pattern, replacement, modified_text)
                        fixed = True

                    issues.append(
                        Issue(
                            id=f"r12_lexicon_{q.number}_{lower_word}",
                            stage="s8_verify",
                            question_id=q.id,
                            rule="lexicon",
                            severity=severity,
                            message=(
                                f"Rule R12: Suspicious word '{word}' in Q{q.number} "
                                f"is edit-distance {min_dist} from domain terms: {best_candidates}"
                                + (" [auto-fixed]" if fixed else "")
                            ),
                            evidence={
                                "original": word,
                                "min_distance": min_dist,
                                "candidates": best_candidates,
                                "auto_fixed": fixed,
                            },
                            candidates=best_candidates,
                        )
                    )

                if modified_text != text:
                    node.texts[lang] = modified_text

    return issues
