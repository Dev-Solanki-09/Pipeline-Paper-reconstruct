"""
Numbering engine, option parsing, chemical formula protection, and monotonicity guard (Phase 6.4).

Provides profile-driven question boundary detection, option extraction, and sequence validation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from examforge.ir.schema import Option
from examforge.layout.redos import SafeRegex, compile_safe_regex

logger = logging.getLogger(__name__)

# Common chemical formula patterns (e.g. "2. SO3", "1. H2O", "3. Fe2O3", "4. KMnO4")
_CHEMICAL_FORMULA_START_RE = re.compile(
    r"^\s*\d{1,2}\s*[.):]\s*([A-Z][a-z]?[0-9]*){2,}(?:\s|\(|$)",
    re.UNICODE,
)

# Known chemical formulas / notations explicitly protected
_KNOWN_FORMULA_TOKENS = {
    "SO3", "SO2", "H2O", "NH3", "CO2", "CH4", "O2", "N2", "H2", "CL2", "FE2O3",
    "KMNO4", "K2CR2O7", "CA(OH)2", "CACL2", "NACL", "CH3COOH", "H2SO4", "HNO3",
    "HCL", "NAOH", "KOH", "NO2", "N2O4", "PCL5", "PCL3",
}

# Prose prefixes indicating that parenthesized numbers are references, not questions/options
_PROSE_PREFIX_RE = re.compile(
    r"^\s*(?:According\s+to\s+|From\s+|Refer\s+to\s+|As\s+shown\s+in\s+|In\s+|Based\s+on\s+|As\s+per\s+)?"
    r"(?:Statement|Equation|Reaction|Case|Condition|Step|Figure|Fig|Part)\s*[-–:]?\s*\(?\d+\)?",
    re.IGNORECASE,
)

_PRE_PAREN_WORD_RE = re.compile(
    r"(?:Statement|Equation|Reaction|Case|Condition|Step|Figure|Fig|Part)\s*[-–:]?\s*$",
    re.IGNORECASE,
)


def is_chemical_formula_or_prose_ref(text: str) -> bool:
    """
    Check if a line or block starting with a number is actually a chemical formula
    (e.g., '2. SO3 is a gas') or contains a prose reference (e.g., 'Statement (1)').
    """
    if not text:
        return False

    first_line = text.strip().split("\n")[0].strip()

    # Check for chemical formula start right after number: e.g. "2. SO3"
    match = re.match(r"^\s*\d{1,2}\s*[.):]\s*([A-Za-z0-9()]+)", first_line)
    if match:
        token = match.group(1).strip().upper()
        if token in _KNOWN_FORMULA_TOKENS:
            return True
        if _CHEMICAL_FORMULA_START_RE.match(first_line):
            # Check if token has mixed letters and digits (e.g. Fe2O3, SO3)
            digits = sum(1 for c in token if c.isdigit())
            letters = sum(1 for c in token if c.isalpha())
            if letters >= 2 and digits >= 1:
                return True

    # Check if the line begins with a prose reference (e.g., 'According to Statement (1)...')
    if _PROSE_PREFIX_RE.match(first_line):
        return True

    return False


def is_valid_monotonic_step(
    current_num: Optional[int],
    next_num: int,
    current_section: Optional[str] = None,
    next_section: Optional[str] = None,
    max_gap: int = 5,
) -> bool:
    """
    Check if progressing from current_num to next_num adheres to monotonicity invariants.
    """
    if current_num is None:
        return next_num > 0

    # Normal sequential step or small allowable gap
    if current_num < next_num <= current_num + max_gap:
        return True

    # Numbering reset allowed on section change
    if next_num == 1 and (current_section != next_section or current_num >= 10):
        return True

    return False


@dataclass
class ParsedQuestionStart:
    number: int
    prefix_length: int
    pattern_name: str


class NumberingEngine:
    """
    Profile-driven numbering detector and option parser with ReDoS safety.
    """

    def __init__(
        self,
        patterns: list[str] | None = None,
        sections: list[str] | None = None,
        label_schemes: list[str] | None = None,
    ):
        raw_patterns = patterns or [
            r"^\s*(\d{1,3})\s*[.):]",
            r"^\s*Q\.?\s*(\d{1,3})\s*[.):]?",
            r"^\s*\((\d{1,3})\)\s*",
            r"^\s*प्र(?:श्न)?\.?\s*(\d{1,3})\s*[.):]?",
        ]
        self.compiled_patterns: list[tuple[SafeRegex, str]] = []
        for pat in raw_patterns:
            try:
                sr = compile_safe_regex(pat, flags=re.MULTILINE)
                self.compiled_patterns.append((sr, pat))
            except Exception as e:
                logger.warning("Skipping invalid or unsafe question pattern %r: %s", pat, e)

        raw_sections = sections or [
            r"SECTION\s+[-–:]?\s*[A-Za-z0-9()]+",
            r"PART\s+[-–:]?\s*[0-9IVX]+",
            r"PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY",
        ]
        try:
            self.section_regex = compile_safe_regex("|".join(raw_sections), flags=re.IGNORECASE)
        except Exception:
            self.section_regex = compile_safe_regex(r"SECTION|PART", flags=re.IGNORECASE)

        self.label_schemes = label_schemes or ["(1)", "(2)", "(3)", "(4)", "(A)", "(B)", "(C)", "(D)"]

    def match_question_start(self, text: str) -> Optional[ParsedQuestionStart]:
        """
        Match text against question-numbering patterns, enforcing chemical/prose guards.
        """
        if not text or is_chemical_formula_or_prose_ref(text):
            return None

        # Disallow starting with an option label (e.g. (A), (1))
        if re.match(r"^\s*\(([A-Da-d1-4])\)", text):
            return None

        for sr, name in self.compiled_patterns:
            match = sr.match(text)
            if match:
                try:
                    num_str = match.group(1)
                    num = int(num_str)
                    return ParsedQuestionStart(
                        number=num,
                        prefix_length=match.end(),
                        pattern_name=name,
                    )
                except (ValueError, IndexError):
                    continue

        return None

    def is_section_header(self, text: str) -> bool:
        """Check if text represents a section header."""
        first_line = text.strip().split("\n")[0].strip()
        if len(first_line) < 80 and self.section_regex.search(first_line):
            if not self.match_question_start(first_line):
                return True
        return False


def parse_options_from_text(
    text: str,
    schemes: list[str] | None = None,
) -> tuple[str, list[Option]]:
    """
    Extract stem text and Option objects according to configured label schemes.
    Supports (1)-(4), (A)-(D), a)-d), (i)-(iv).
    """
    if not text:
        return "", []

    # Patterns matching option delimiters
    # Line-anchored preferred
    line_alpha = list(re.finditer(r"(?:^|\n)\s*\(([A-Da-d])\)\s*", text))
    line_num = list(re.finditer(r"(?:^|\n)\s*\(([1-6])\)\s*", text))

    matches = line_alpha if len(line_alpha) >= 2 else (line_num if len(line_num) >= 2 else [])

    # If line-anchored didn't find >= 2, try inline
    if len(matches) < 2:
        inline_alpha = list(re.finditer(r"(?:^|[\s\n])\(([A-Da-d])\)\s*", text))
        inline_num = list(re.finditer(r"(?:^|[\s\n])\(([1-6])\)\s*", text))
        matches = inline_alpha if len(inline_alpha) >= 2 else (inline_num if len(inline_num) >= 2 else [])

    # Filter out matches preceded by prose indicator words (e.g. Statement (1))
    valid_matches = []
    for m in matches:
        start_idx = m.start()
        prefix = text[max(0, start_idx - 25):start_idx]
        if not _PRE_PAREN_WORD_RE.search(prefix):
            valid_matches.append(m)

    if len(valid_matches) < 2:
        return text.strip(), []

    # Stem is everything before the first valid option match
    stem = text[:valid_matches[0].start()].strip()

    options: list[Option] = []
    for i, m in enumerate(valid_matches):
        label = m.group(1).upper()
        content_start = m.end()
        content_end = valid_matches[i + 1].start() if i + 1 < len(valid_matches) else len(text)
        opt_text = text[content_start:content_end].strip()
        options.append(Option(label=label, text=opt_text, text_str_en=opt_text))

    return stem, options
