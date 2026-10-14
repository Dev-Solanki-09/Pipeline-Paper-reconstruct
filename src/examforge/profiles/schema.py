"""
Declarative ExamProfile schema for ExamForge v2.

Defines the complete profile configuration allowing any exam paper to be
ingested and processed without hard-coded exam assumptions in stage logic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from examforge.ir.schema import QuestionKind

Maturity = Literal["verified", "experimental"]
LanguageLayout = Literal["monolingual", "parallel_columns", "interleaved", "separate_sections"]
ReadingOrder = Literal["xy_cut", "columns_ltr", "columns_rtl", "parallel"]
ResetPolicy = Literal["per_section", "continuous", "per_part"]
OptionLayoutPref = Literal["vertical", "grid", "inline", "auto"]
ImageOptionPolicy = Literal["allow", "disallow", "crop_only"]
WatermarkMode = Literal["auto", "subtract", "mask", "ignore"]
ComputeTier = Literal["lite", "standard", "gpu"]


class LanguageProfileConfig(BaseModel):
    """Language and script configuration."""

    model_config = ConfigDict(frozen=True)

    code: str = "en"
    script: str = "Latn"
    direction: Literal["ltr", "rtl"] = "ltr"


class LayoutProfileConfig(BaseModel):
    """Layout, column, and orientation policies."""

    model_config = ConfigDict(frozen=True)

    columns: int | Literal["auto"] = 1
    spans_allowed: bool = True
    reading_order: ReadingOrder = "columns_ltr"
    orientation_policy: str = "portrait"

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, v: int | str) -> int | str:
        if isinstance(v, int) and v < 1:
            raise ValueError("columns must be >= 1 or 'auto'")
        if isinstance(v, str) and v != "auto":
            raise ValueError("columns must be an integer >= 1 or 'auto'")
        return v


class NumberingProfileConfig(BaseModel):
    """Question numbering and section hierarchy rules."""

    model_config = ConfigDict(frozen=True)

    patterns: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    reset_policy: ResetPolicy = "continuous"
    nesting_labels: list[str] = Field(default_factory=lambda: ["(a)", "(b)", "(c)", "(d)"])


class OptionsProfileConfig(BaseModel):
    """Option labeling, layout, and count expectations."""

    model_config = ConfigDict(frozen=True)

    label_schemes: list[str] = Field(default_factory=lambda: ["(1)", "(2)", "(3)", "(4)"])
    count_min: int = 2
    count_max: int = 5
    count_typical: int = 4
    layout_preference: OptionLayoutPref = "auto"
    image_option_policy: ImageOptionPolicy = "allow"


class WatermarkProfileConfig(BaseModel):
    """Watermark detection and removal policy."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    mode: WatermarkMode = "auto"
    patterns: list[str] = Field(default_factory=list)


class FurnitureBrandingProfileConfig(BaseModel):
    """Repeating header, footer, coaching watermark, and branding policies."""

    model_config = ConfigDict(frozen=True)

    headers: list[str] = Field(default_factory=list)
    footers: list[str] = Field(default_factory=list)
    branding: list[str] = Field(default_factory=list)
    watermark: WatermarkProfileConfig = Field(default_factory=WatermarkProfileConfig)


class MarkingProfileConfig(BaseModel):
    """Default marking scheme configuration."""

    model_config = ConfigDict(frozen=True)

    positive: float = 4.0
    negative: float = -1.0
    partial: bool = False


class RuleOverrideConfig(BaseModel):
    """Per-rule configuration and threshold overrides."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    severity: Literal["blocker", "warn", "info"] = "blocker"
    threshold: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class OutputProfileConfig(BaseModel):
    """Packaging and presentation preferences."""

    model_config = ConfigDict(frozen=True)

    template: str = "exam.html.j2"
    layout_mode: str = "single_column"
    exporters: list[str] = Field(default_factory=lambda: ["html", "json"])
    include_answers: bool = False


_KIND_MAP: dict[str, QuestionKind] = {
    # Values
    "mcq1": QuestionKind.SINGLE_CORRECT,
    "mcqn": QuestionKind.MULTI_CORRECT,
    "numeric": QuestionKind.NUMERICAL,
    "match": QuestionKind.MATCH,
    "assertion": QuestionKind.ASSERTION_REASON,
    "passage": QuestionKind.PASSAGE_BASED,
    "integer": QuestionKind.INTEGER,
    "statement_based": QuestionKind.STATEMENT_BASED,
    "fill_blank": QuestionKind.FILL_BLANK,
    "true_false": QuestionKind.TRUE_FALSE,
    "short_answer": QuestionKind.SHORT_ANSWER,
    "long_answer": QuestionKind.LONG_ANSWER,
    "other": QuestionKind.OTHER,
    # Aliases
    "single_correct": QuestionKind.SINGLE_CORRECT,
    "multi_correct": QuestionKind.MULTI_CORRECT,
    "mcq_single": QuestionKind.SINGLE_CORRECT,
    "mcq_multi": QuestionKind.MULTI_CORRECT,
    "numerical": QuestionKind.NUMERICAL,
    "assertion_reason": QuestionKind.ASSERTION_REASON,
    "passage_based": QuestionKind.PASSAGE_BASED,
}


class ExamProfile(BaseModel):
    """
    Complete declarative specification for an exam paper family.

    Enables ingestion of any exam paper without modifying core stage code.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    profile_version: str = "1.0.0"
    engine_min_version: str = "2.0.0"
    maturity: Maturity = "experimental"
    extends: list[str] = Field(default_factory=list)

    languages: list[LanguageProfileConfig] = Field(
        default_factory=lambda: [LanguageProfileConfig(code="en", script="Latn", direction="ltr")]
    )
    language_layout: LanguageLayout = "monolingual"

    layout: LayoutProfileConfig = Field(default_factory=LayoutProfileConfig)
    numbering: NumberingProfileConfig = Field(default_factory=NumberingProfileConfig)
    options: OptionsProfileConfig = Field(default_factory=OptionsProfileConfig)
    furniture_branding: FurnitureBrandingProfileConfig = Field(
        default_factory=FurnitureBrandingProfileConfig
    )

    expected_kinds: list[QuestionKind] = Field(default_factory=list)

    @field_validator("expected_kinds", mode="before")
    @classmethod
    def normalize_expected_kinds(cls, v: Any) -> list[QuestionKind]:
        if not isinstance(v, list):
            return v
        results: list[QuestionKind] = []
        for item in v:
            if isinstance(item, QuestionKind):
                results.append(item)
            elif isinstance(item, str):
                normalized = item.strip().lower()
                if normalized in _KIND_MAP:
                    results.append(_KIND_MAP[normalized])
                else:
                    results.append(QuestionKind(normalized))
            else:
                results.append(item)
        return results

    marking: MarkingProfileConfig = Field(default_factory=MarkingProfileConfig)
    answer_key_patterns: list[str] = Field(default_factory=list)

    rules: dict[str, RuleOverrideConfig] = Field(default_factory=dict)
    autofix_allowlist: list[str] = Field(default_factory=list)

    output: OutputProfileConfig = Field(default_factory=OutputProfileConfig)

    requires: list[str] = Field(default_factory=list)
    capability_policy: Literal["fail", "downgrade", "warn"] = "warn"
    compute: ComputeTier = "standard"
