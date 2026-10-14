"""Answer key parsing in multiple styles (inline, grid, table, text)."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

# Devanagari digits to ASCII digits
_DEVA_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}


def _deva_to_ascii(s: str) -> str:
    """Convert Devanagari numerals in string to ASCII digits."""
    return "".join(_DEVA_DIGITS.get(ch, ch) for ch in s)


def _to_int(s: str) -> int:
    """Parse integer from ASCII or Devanagari numerals."""
    ascii_s = _deva_to_ascii(s.strip())
    # Extract consecutive digits
    m = re.search(r"\d+", ascii_s)
    if not m:
        raise ValueError(f"No digits found in {s!r}")
    return int(m.group(0))


@dataclass
class ParsedKeyEntry:
    """A parsed single answer entry from an answer key."""

    question_number: int
    section: str | None = None
    options: list[str] = field(default_factory=list)
    numeric_value: float | None = None
    numeric_range: tuple[float, float] | None = None
    raw_answer: str = ""
    is_bonus: bool = False
    is_dropped: bool = False


def _populate_entry(raw: str, entry: ParsedKeyEntry) -> ParsedKeyEntry:
    """Parse the raw answer string and populate entry attributes."""
    cleaned = raw.strip()
    entry.raw_answer = cleaned

    lower = cleaned.lower()
    # 1. Check Bonus / Dropped
    if "bonus" in lower:
        entry.is_bonus = True
        return entry
    if any(k in lower for k in ["drop", "dropped", "none", "cancel", "cancelled", "रद्द"]):
        entry.is_dropped = True
        return entry

    # 2. Check Numeric Range: e.g. "3.14 - 3.16" or "10.5 to 11.0" or "3.14 to 3.16"
    range_match = re.match(
        r"^[\[\(]?\s*(-?\d+(?:\.\d+)?)\s*(?:-|to|–|—)\s*(-?\d+(?:\.\d+)?)\s*[\]\)]?$",
        cleaned,
        re.IGNORECASE,
    )
    if range_match:
        try:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            entry.numeric_range = (low, high)
            return entry
        except ValueError:
            pass

    # 3. Check for explicitly parenthesized option e.g. "(3)" or "(B)"
    paren_match = re.match(r"^\(([A-Za-z0-9]|[\u0900-\u097F])\)$", cleaned)
    if paren_match:
        val = paren_match.group(1)
        entry.raw_answer = val
        entry.options = [val.upper() if val.isascii() and val.isalpha() else val]
        return entry

    # 4. Check for multi-correct options: e.g. "A, C", "(B), (D)", "A or B"
    delimiters = re.compile(r"\s*(?:,|/|;|\bor\b|\band\b)\s*|\s+", re.IGNORECASE)
    raw_parts = [p.strip("() \t") for p in delimiters.split(cleaned) if p.strip("() \t")]
    parts = [p for p in raw_parts if p.lower() not in {"or", "and"}]
    if len(parts) > 1:
        # Check if parts are valid option labels (letters or Hindi consonants)
        valid_parts = [
            p.upper() if (p.isascii() and p.isalpha()) else p
            for p in parts
            if len(p) <= 2
        ]
        if len(valid_parts) == len(parts):
            entry.options = valid_parts
            return entry

    # 5. Check for single float or integer without parens
    num_match = re.match(r"^-?\d+(?:\.\d+)?$", cleaned)
    if num_match:
        # If it has a decimal or is > 4 (unlikely to be a 4-choice option), treat as numeric
        # If exactly an integer 1-4, it could be option or numeric.
        try:
            val = float(cleaned)
            entry.numeric_value = val
        except ValueError:
            pass
        return entry

    # 6. Single option letter / symbol
    # Strip any enclosing parens
    unwrapped = cleaned.strip("() \t")
    if unwrapped:
        norm_val = unwrapped.upper() if (unwrapped.isascii() and unwrapped.isalpha()) else unwrapped
        entry.options = [norm_val]

    return entry


def parse_answer_key_inline(text: str) -> list[ParsedKeyEntry]:
    """
    Parse inline answer markers inside question text.

    Matches patterns like:
    Question 1: ...
    Ans. (3)
    Question 2: ...
    Answer: (B)
    """
    entries: list[ParsedKeyEntry] = []
    lines = text.splitlines()
    current_q: int | None = None
    current_section: str | None = None

    q_pattern = re.compile(
        r"^(?:Question|Q\.?|प्र\.?|प्रश्न)\s*(\d+|[०-९]+)",
        re.IGNORECASE,
    )
    ans_pattern = re.compile(
        r"^(?:Ans(?:wer)?\.?|उत्तर)\s*[:.\-]?\s*(.+)$",
        re.IGNORECASE,
    )
    section_pattern = re.compile(
        r"^(?:Section|Part|खण्ड|भाग)\s*([A-Za-z0-9]+)",
        re.IGNORECASE,
    )

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        sec_m = section_pattern.match(line_str)
        if sec_m:
            current_section = sec_m.group(1)
            continue

        q_m = q_pattern.match(line_str)
        if q_m:
            current_q = _to_int(q_m.group(1))
            continue

        ans_m = ans_pattern.match(line_str)
        if ans_m and current_q is not None:
            raw_val = ans_m.group(1).strip()
            entry = ParsedKeyEntry(
                question_number=current_q,
                section=current_section,
            )
            _populate_entry(raw_val, entry)
            entries.append(entry)
            current_q = None

    return entries


def parse_answer_key_grid(text: str) -> list[ParsedKeyEntry]:
    """
    Parse dense grid answer keys.

    Matches patterns like:
    '1-A 2-C 3-D 4-B' or '१-ख २-ग ३-क'
    """
    entries: list[ParsedKeyEntry] = []
    # Token matches: Q_NUM followed by separator [-:.)] followed by ANSWER
    pattern = re.compile(
        r"(?:Q\.?)?(\d+|[०-९]+)\s*[-:.=]\s*(\([^\)]+\)|[^\s]+)"
    )

    for m in pattern.finditer(text):
        q_num = _to_int(m.group(1))
        raw_ans = m.group(2).strip()
        entry = ParsedKeyEntry(question_number=q_num)
        _populate_entry(raw_ans, entry)
        entries.append(entry)

    return entries


def parse_answer_key_table(rows: list[list[Any]]) -> list[ParsedKeyEntry]:
    """
    Parse two-column or multi-column answer key table rows.

    Expected format: [[Q, Ans], [1, A], [2, B], ...]
    """
    entries: list[ParsedKeyEntry] = []

    for row in rows:
        if len(row) < 2:
            continue
        q_cell = str(row[0]).strip()
        ans_cell = str(row[1]).strip()

        # Check if q_cell contains digits
        if not re.search(r"(\d+|[०-९]+)", q_cell):
            # Header row
            continue

        try:
            q_num = _to_int(q_cell)
        except ValueError:
            continue

        entry = ParsedKeyEntry(question_number=q_num)
        _populate_entry(ans_cell, entry)
        entries.append(entry)

    return entries


def parse_answer_key_text(text: str) -> list[ParsedKeyEntry]:
    """
    Parse multi-line answer key text.

    Matches lines like:
    1: A, C
    Q21: 3.14 - 3.16
    10: Dropped
    """
    entries: list[ParsedKeyEntry] = []
    current_section: str | None = None

    line_pattern = re.compile(
        r"^(?:(?:Q|Question|प्र\.?|प्रश्न)\.?\s*)?(\d+|[०-९]+)\s*[-:.)]\s*(.+)$",
        re.IGNORECASE,
    )
    section_pattern = re.compile(
        r"^(?:Section|Part|खण्ड|भाग)\s*([A-Za-z0-9]+)",
        re.IGNORECASE,
    )

    for line in text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue

        sec_m = section_pattern.match(line_str)
        if sec_m:
            current_section = sec_m.group(1)
            continue

        m = line_pattern.match(line_str)
        if m:
            q_num = _to_int(m.group(1))
            raw_ans = m.group(2).strip()
            entry = ParsedKeyEntry(
                question_number=q_num,
                section=current_section,
            )
            _populate_entry(raw_ans, entry)
            entries.append(entry)

    return entries
