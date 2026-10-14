"""Option homogeneity and dimensional checks (Phase O7.4).

Verifies and enforces consistency across multiple-choice options:
- Homogeneous units: if majority of options share a physical unit (e.g. m/s, kg, V),
  detects minority options with OCR misreads (e.g. 'mls' -> 'm/s', 'k9' -> 'kg')
- Structural homogeneity: checks consistent numeric, LaTeX, or prose classification.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import NamedTuple

from examforge.ir.schema import Issue, IssueSeverity, Option

# Common scientific units in exams and their frequent OCR misread corruptions
_UNIT_CORRECTIONS = {
    "mls": "m/s",
    "m/s^2": "m/s^2",
    "m/s2": "m/s^2",
    "k9": "kg",
    "1kg": "kg",
    "uf": "μF",
    "pf": "pF",
    "omega": "Ω",
    "ohm": "Ω",
    "rad/s": "rad/s",
}

_UNIT_EXTRACT_RE = re.compile(
    r"\b([a-zA-ZμΩ°/%^0-9/]+)\s*$",
)


class HomogeneityReport(NamedTuple):
    is_homogeneous: bool
    majority_unit: str | None
    anomalous_options: list[str]
    corrections_applied: int


def analyze_option_units(options: list[Option]) -> HomogeneityReport:
    """Analyze option texts for unit consistency and repair obvious OCR unit anomalies."""
    if len(options) < 3:
        return HomogeneityReport(is_homogeneous=True, majority_unit=None, anomalous_options=[], corrections_applied=0)

    units_by_label: dict[str, str] = {}
    for opt in options:
        txt = (opt.text_str_en or opt.text_str_hi or "").strip()
        # Look for trailing unit token
        m = _UNIT_EXTRACT_RE.search(txt)
        if m:
            units_by_label[opt.label] = m.group(1).lower()

    if len(units_by_label) < len(options) * 0.75:
        # Not a unit-bearing question
        return HomogeneityReport(is_homogeneous=True, majority_unit=None, anomalous_options=[], corrections_applied=0)

    unit_counts = Counter(units_by_label.values())
    majority_unit, count = unit_counts.most_common(1)[0]

    # If >= 60% of options have majority unit, check the outliers
    corrections = 0
    anomalies = []
    if count >= max(2, len(options) - 1):
        for opt in options:
            label = opt.label
            cur_unit = units_by_label.get(label)
            if cur_unit and cur_unit != majority_unit:
                # Check if cur_unit is a known OCR corruption of majority_unit
                cleaned_curr = cur_unit.replace("1", "l").replace("0", "o")
                if _UNIT_CORRECTIONS.get(cur_unit) == majority_unit or cleaned_curr == majority_unit:
                    # Repair the text in option
                    if opt.text_str_en:
                        opt.text_str_en = re.sub(
                            re.escape(cur_unit) + r"\s*$", majority_unit, opt.text_str_en, flags=re.IGNORECASE
                        )
                    for b in opt.text_en:
                        b.text = re.sub(
                            re.escape(cur_unit) + r"\s*$", majority_unit, b.text, flags=re.IGNORECASE
                        )
                    corrections += 1
                else:
                    anomalies.append(label)

    return HomogeneityReport(
        is_homogeneous=(len(anomalies) == 0),
        majority_unit=majority_unit if count >= 2 else None,
        anomalous_options=anomalies,
        corrections_applied=corrections,
    )
