"""
Number and unit canonicalization shared with verifier R10.
"""

from __future__ import annotations

import re


def canonicalize_number(s: str) -> str:
    """
    Canonicalize numeric strings for deterministic comparisons.

    - Removes thousands commas (e.g. 10,000 -> 10000)
    - Strips leading zeros for integers (e.g. 05 -> 5)
    - Strips redundant trailing zeros in decimal representation (e.g. 3.140 -> 3.14, 10.0 -> 10)
    """
    if not s:
        return s

    raw = s.strip().replace(",", "")
    sign = ""
    if raw.startswith("+"):
        raw = raw[1:]
    elif raw.startswith("-"):
        sign = "-"
        raw = raw[1:]

    # Decimal number
    if "." in raw:
        integer_part, decimal_part = raw.split(".", 1)
        # Strip leading zeros from integer part
        integer_part = integer_part.lstrip("0") or "0"
        # Strip trailing zeros from decimal part
        decimal_part = decimal_part.rstrip("0")
        if not decimal_part:
            return f"{sign}{integer_part}"
        return f"{sign}{integer_part}.{decimal_part}"

    # Pure integer
    if raw.isdigit():
        integer_part = raw.lstrip("0") or "0"
        return f"{sign}{integer_part}"

    return f"{sign}{raw}"


def canonicalize_unit(s: str) -> str:
    """
    Canonicalize physical unit strings into standard power notation.

    e.g. 'm/s' -> 'm s^{-1}', 'km/h' -> 'km h^{-1}', 'N/m^2' -> 'N m^{-2}'.
    """
    if not s:
        return s

    u = s.strip()
    # Remove \text{ and } wrapper if present
    u = re.sub(r"\\text\{\s*([^}]+)\s*\}", r"\1", u).strip()

    # Convert /unit^n or /unit to unit^{-n}
    def _repl_slash(m: re.Match) -> str:
        unit = m.group(1)
        exp = m.group(2)
        if exp:
            exp_val = exp.strip("{}")
            return f" {unit}^{{-{exp_val}}}"
        return f" {unit}^{{-1}}"

    u = re.sub(r"\/([a-zA-Z]+)(?:\^(\d+|\{\d+\}))?", _repl_slash, u)
    # Normalize multiple spaces
    u = re.sub(r"\s+", " ", u).strip()
    return u


def canonicalize_value_with_unit(s: str) -> tuple[str, str]:
    """
    Split and canonicalize a value and its unit.

    Returns:
        tuple of (canonical_number, canonical_unit)
    """
    if not s:
        return "", ""

    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(.*)$", s.strip())
    if not m:
        return s.strip(), ""

    num_str = canonicalize_number(m.group(1))
    unit_str = canonicalize_unit(m.group(2))
    return num_str, unit_str
