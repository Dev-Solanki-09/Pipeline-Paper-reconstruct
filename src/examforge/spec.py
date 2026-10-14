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
    def default(cls, verifiers_v2: bool = False) -> Spec:
        """Return the default spec with standard rules (and v2 verifiers if requested)."""
        rules = {
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
        }
        if verifiers_v2:
            rules.update({
                "R10_language_consistency": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="language_consistency",
                ),
                "R11_text_layer_agreement": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="text_layer_agreement",
                ),
                "R12_lexicon": Rule(
                    severity=RuleSeverity.WARN,
                    check="lexicon",
                ),
                "R13_render_check": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="render_check",
                ),
                "R14_sequence_gaps": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="sequence_gaps",
                ),
                "R15_structure_consistency": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="structure_consistency",
                ),
                "R16_answer_binding": Rule(
                    severity=RuleSeverity.BLOCKER,
                    check="answer_binding",
                ),
            })
        return cls(
            spec_version=2 if verifiers_v2 else 1,
            rules=rules,
        )

    @classmethod
    def v2(cls) -> Spec:
        """Return the v2 spec with all 15 rules active."""
        return cls.default(verifiers_v2=True)

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


def compute_spec_hash(
    engine_version: str,
    profile: Any,
    enabled_rules: dict[str, Any] | list[str] | None = None,
    compute_tier: str = "standard",
) -> str:
    """
    Deterministic spec hash per Phase 3.8:
    spec_hash = hash(engine_version + profile (resolved) + enabled_rules + compute_tier).
    Checkpoints invalidate when this hash changes.
    """
    import json

    if hasattr(profile, "model_dump"):
        prof_data = profile.model_dump(mode="json")
    elif isinstance(profile, dict):
        prof_data = profile
    else:
        prof_data = str(profile)

    rules_rep: Any
    if isinstance(enabled_rules, (list, set)):
        rules_rep = sorted(enabled_rules)
    elif isinstance(enabled_rules, dict):
        rules_rep = {k: str(v) for k, v in sorted(enabled_rules.items())}
    else:
        rules_rep = {}

    payload = {
        "engine_version": engine_version,
        "profile": prof_data,
        "enabled_rules": rules_rep,
        "compute_tier": compute_tier,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

