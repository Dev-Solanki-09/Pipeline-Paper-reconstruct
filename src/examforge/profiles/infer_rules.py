"""
Phase 13.2 — Deterministic Profile Inference.

Infers an initial ExamProfile and per-field confidence scores from
the document fingerprint and structure without LLM tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from examforge.ir.schema import ExamDocument
from examforge.profiles.fingerprint import DocumentFingerprint
from examforge.profiles.schema import (
    ExamProfile,
    LanguageProfileConfig,
    LayoutProfileConfig,
    NumberingProfileConfig,
    OptionsProfileConfig,
)


@dataclass
class ProfileInferenceResult:
    """Output of deterministic profile inference with audit confidences."""

    profile: ExamProfile
    field_confidences: dict[str, float]
    overall_confidence: float
    low_confidence_fields: list[str]


_SECTION_KEYWORDS = [
    re.compile(r"(?i)\b(?:SECTION|PART)\s+[A-Z0-9IVX]+\b"),
    re.compile(r"(?i)\b(?:PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY|BOTANY|ZOOLOGY)\b"),
]


def infer_profile_deterministic(
    doc: ExamDocument,
    fp: DocumentFingerprint,
    confidence_threshold: float = 0.85,
) -> ProfileInferenceResult:
    """
    Infer ExamProfile fields from DocumentFingerprint and document blocks.
    """
    field_confidences: dict[str, float] = {}

    # 1. Languages
    languages: list[LanguageProfileConfig] = []
    scripts = fp.script_distribution
    if scripts.get("Latn", 0.0) >= 0.05 or not scripts:
        languages.append(LanguageProfileConfig(code="en", script="Latn", direction="ltr"))
    if scripts.get("Deva", 0.0) >= 0.05:
        languages.append(LanguageProfileConfig(code="hi", script="Deva", direction="ltr"))
    if scripts.get("Arab", 0.0) >= 0.05:
        languages.append(LanguageProfileConfig(code="ur", script="Arab", direction="rtl"))
    if scripts.get("Taml", 0.0) >= 0.05:
        languages.append(LanguageProfileConfig(code="ta", script="Taml", direction="ltr"))
    if scripts.get("Telu", 0.0) >= 0.05:
        languages.append(LanguageProfileConfig(code="te", script="Telu", direction="ltr"))

    if not languages:
        languages.append(LanguageProfileConfig(code="en", script="Latn", direction="ltr"))
        field_confidences["languages"] = 0.50
    else:
        field_confidences["languages"] = 0.95

    # 2. Layout and Columns
    cols = fp.estimated_columns
    field_confidences["layout.columns"] = 0.90 if fp.page_count_sampled > 0 else 0.50
    layout = LayoutProfileConfig(
        columns=cols,
        reading_order="columns_ltr",
    )

    # 3. Language Layout
    if len(languages) == 1:
        lang_layout = "monolingual"
        field_confidences["language_layout"] = 0.95
    elif cols >= 2:
        lang_layout = "parallel_columns"
        field_confidences["language_layout"] = 0.90
    else:
        lang_layout = "interleaved"
        field_confidences["language_layout"] = 0.85

    # 4. Numbering
    num_conf = 0.90
    if fp.dominant_numbering == "dot":
        patterns = [r"^\s*(\d{1,3})\.\s*"]
    elif fp.dominant_numbering == "q_prefix":
        patterns = [r"(?i)^\s*Q\.?\s*(\d{1,3})[\.\s]"]
    elif fp.dominant_numbering == "paren":
        patterns = [r"^\s*\((\d{1,3})\)\s*"]
    elif fp.dominant_numbering == "hindi_prashna":
        patterns = [r"^\s*प्रश्न\s*(\d{1,3})[\.\s]"]
    else:
        patterns = [r"^\s*(\d{1,3})\.\s*"]
        num_conf = 0.40  # low confidence default

    field_confidences["numbering.patterns"] = num_conf

    # Detect sections from headers/blocks
    sections: list[str] = []
    for b in doc.blocks:
        for p in _SECTION_KEYWORDS:
            m = p.search(b.text)
            if m:
                s_name = m.group(0).upper().strip()
                if s_name not in sections:
                    sections.append(s_name)

    numbering = NumberingProfileConfig(
        patterns=patterns,
        sections=sections,
        reset_policy="continuous",
    )

    # 5. Options
    opt_conf = 0.92
    if fp.dominant_option_scheme == "alpha_paren":
        label_schemes = ["(A)", "(B)", "(C)", "(D)"]
    elif fp.dominant_option_scheme == "digit_paren":
        label_schemes = ["(1)", "(2)", "(3)", "(4)"]
    elif fp.dominant_option_scheme == "alpha_dot":
        label_schemes = ["A.", "B.", "C.", "D."]
    elif fp.dominant_option_scheme == "hindi_paren":
        label_schemes = ["(क)", "(ख)", "(ग)", "(घ)"]
    else:
        label_schemes = ["(1)", "(2)", "(3)", "(4)"]
        opt_conf = 0.40  # low confidence default

    field_confidences["options.label_schemes"] = opt_conf
    options = OptionsProfileConfig(label_schemes=label_schemes)

    # 6. Overall Confidence & Result
    overall = sum(field_confidences.values()) / max(1, len(field_confidences))
    low_conf = [k for k, v in field_confidences.items() if v < confidence_threshold]

    prof_id = f"auto_{fp.doc_hash[:8]}"
    profile = ExamProfile(
        id=prof_id,
        name=f"Auto-Inferred Profile {prof_id}",
        maturity="experimental",
        languages=languages,
        language_layout=lang_layout,
        layout=layout,
        numbering=numbering,
        options=options,
    )

    return ProfileInferenceResult(
        profile=profile,
        field_confidences=field_confidences,
        overall_confidence=round(overall, 3),
        low_confidence_fields=low_conf,
    )
