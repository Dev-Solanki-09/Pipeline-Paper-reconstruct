"""
ExamForge specification: the frozen rule set that every run must satisfy.

The spec defines rules (each with a severity and a check name), modes
(fast/max), and thresholds. For v1 this is a simple Pydantic model loaded
from YAML — the full spec-patching and diff-approval workflow comes later.

Design:
- Rules are identified by string IDs (e.g. "R01_no_furniture").
- Each rule has a severity (blocker/warn) and a check identifier.
- The spec hash is recorded in the manifest for traceability.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RuleSeverity(str, Enum):
    BLOCKER = "blocker"
    WARN = "warn"


class Rule(BaseModel):
    """A single spec rule."""

    severity: RuleSeverity = RuleSeverity.BLOCKER
    check: str = ""  # validator function name
    params: dict[str, Any] = Field(default_factory=dict)


class ModeConfig(BaseModel):
    """Per-mode settings (fast vs max)."""

    engines: list[str] = Field(default=["E1"])
    second_engine: str = "on_flag"  # "on_flag" or "always"
    audit_sample: float = 0.05


class Spec(BaseModel):
    """
    The frozen specification for an ExamForge run.

    Every rule names a check and a severity. The spec hash is written
    into the HTML metadata and the run manifest.
    """

    spec_version: int = 1
    rules: dict[str, Rule] = Field(default_factory=dict)
    modes: dict[str, ModeConfig] = Field(default_factory=lambda: {
        "fast": ModeConfig(engines=["E1"], second_engine="on_flag", audit_sample=0.05),
        "max": ModeConfig(engines=["E1", "E2"], second_engine="always", audit_sample=0.10),
    })

    @classmethod
    def load(cls, path: Path) -> Spec:
        """Load a spec from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Spec file {path} must contain a YAML mapping")
        return cls(**data)

    @classmethod
    def default(cls) -> Spec:
        """Return the default spec with all standard rules."""
        return cls(
            spec_version=1,
            rules={
                "R01_no_furniture": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="no_headers_footers_page_numbers",
                ),
                "R02_no_branding": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="no_brand_text_or_logo",
                ),
                "R03_no_watermark": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="watermark_residual",
                    params={"max_corr": 0.05},
                ),
                "R04_continuous": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="no_page_wrappers_or_breaks",
                ),
                "R05_bilingual": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="en_hi_pairs_complete",
                ),
                "R06_complete": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="numbering_continuity",
                ),
                "R07_formulas": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="formula_roundtrip",
                ),
                "R08_figures": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="figure_clean_border_and_present",
                ),
                "R09_unicode": Rule(
                    severity=RuleSeverity.WARN,
                    check="devanagari_nfc_and_lexicon",
                ),
            },
        )

    def hash(self) -> str:
        """Deterministic hash of the spec for traceability."""
        # Serialize to sorted JSON for determinism
        raw = self.model_dump_json(indent=None)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def blocker_rules(self) -> dict[str, Rule]:
        """Return only blocker-severity rules."""
        return {k: v for k, v in self.rules.items() if v.severity == RuleSeverity.BLOCKER}

    def get_mode(self, mode_name: str) -> ModeConfig:
        """Get mode config, falling back to 'fast' if unknown."""
        return self.modes.get(mode_name, self.modes.get("fast", ModeConfig()))
