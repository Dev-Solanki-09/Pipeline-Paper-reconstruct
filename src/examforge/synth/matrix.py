"""Universality Matrix: Greedy pairwise covering array generator.

Generates a minimal set of exam families that cover all pairwise combinations
of layout, numbering, language, orientation, and option axes.
"""

from __future__ import annotations

import itertools
import random
from pathlib import Path
from typing import Any

import yaml

from examforge.profiles.schema import (
    ExamProfile,
    FurnitureBrandingProfileConfig,
    LanguageProfileConfig,
    LayoutProfileConfig,
    NumberingProfileConfig,
    OptionsProfileConfig,
    OutputProfileConfig,
    WatermarkProfileConfig,
)

AXES: dict[str, list[Any]] = {
    "columns": [1, 2, 3],
    "language_layout": ["monolingual", "parallel_columns", "interleaved", "separate_sections"],
    "numbering_style": ["dot", "parentheses", "q_prefix"],
    "option_style": ["num_paren", "alpha_paren", "roman_paren"],
    "orientation": ["portrait", "landscape"],
    "watermark": ["none", "text_diagonal", "center_logo"],
    "primary_kind": ["mcq1", "assertion_reason", "match", "numerical"],
}


def generate_pairwise_covering_array(
    axes: dict[str, list[Any]] | None = None,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Greedy algorithm to construct a covering array where all pairs of parameter values
    from different axes appear together at least once.
    """
    param_axes = axes or AXES
    axis_names = list(param_axes.keys())

    # Build all required pairs: (axis1, val1, axis2, val2) where axis1 < axis2
    uncovered_pairs: set[tuple[str, Any, str, Any]] = set()
    for (a1, a2) in itertools.combinations(axis_names, 2):
        for v1 in param_axes[a1]:
            for v2 in param_axes[a2]:
                uncovered_pairs.add((a1, v1, a2, v2))

    rng = random.Random(seed)
    test_cases: list[dict[str, Any]] = []

    # Greedy candidate generation
    while uncovered_pairs:
        best_candidate: dict[str, Any] | None = None
        best_covered_count = -1

        # Sample multiple randomized candidates and pick the one covering the most uncovered pairs
        candidates_to_try = 100
        for _ in range(candidates_to_try):
            candidate = {a: rng.choice(param_axes[a]) for a in axis_names}
            # Count covered pairs
            count = 0
            for (a1, a2) in itertools.combinations(axis_names, 2):
                if (a1, candidate[a1], a2, candidate[a2]) in uncovered_pairs:
                    count += 1
            if count > best_covered_count:
                best_covered_count = count
                best_candidate = candidate

        if best_candidate is None or best_covered_count == 0:
            # Fallback: Pick an uncovered pair directly and fill in remaining axes
            a1, v1, a2, v2 = next(iter(uncovered_pairs))
            best_candidate = {a: rng.choice(param_axes[a]) for a in axis_names}
            best_candidate[a1] = v1
            best_candidate[a2] = v2

        # Record candidate and remove covered pairs
        test_cases.append(best_candidate)
        for (a1, a2) in itertools.combinations(axis_names, 2):
            uncovered_pairs.discard((a1, best_candidate[a1], a2, best_candidate[a2]))

    return test_cases


def build_profile_for_combination(idx: int, config: dict[str, Any]) -> ExamProfile:
    """Map a parameter combination dictionary into a valid ExamProfile object."""
    family_id = f"univ_family_{idx+1:02d}"

    # Numbering patterns
    num_style = config["numbering_style"]
    if num_style == "dot":
        num_patterns = [r"^\s*(\d{1,3})\s*[.]"]
    elif num_style == "parentheses":
        num_patterns = [r"^\s*\((\d{1,3})\)\s*"]
    else:
        num_patterns = [r"^\s*Q\.?\s*(\d{1,3})\s*[.]?"]

    # Option label schemes
    opt_style = config["option_style"]
    if opt_style == "num_paren":
        label_schemes = ["(1)", "(2)", "(3)", "(4)"]
    elif opt_style == "alpha_paren":
        label_schemes = ["(A)", "(B)", "(C)", "(D)"]
    else:
        label_schemes = ["(i)", "(ii)", "(iii)", "(iv)"]

    # Languages
    lang_layout = config["language_layout"]
    if lang_layout == "monolingual":
        langs = [LanguageProfileConfig(code="en", script="Latn", direction="ltr")]
    else:
        langs = [
            LanguageProfileConfig(code="en", script="Latn", direction="ltr"),
            LanguageProfileConfig(code="hi", script="Deva", direction="ltr"),
        ]

    wm = config["watermark"]
    watermark_cfg = WatermarkProfileConfig(
        enabled=(wm != "none"),
        mode="subtract" if wm != "none" else "ignore",
        patterns=["CONFIDENTIAL", "TEST"] if wm == "text_diagonal" else ["LOGO"],
    )

    profile = ExamProfile(
        id=family_id,
        name=f"Universal Benchmark Family {idx+1:02d}",
        profile_version="2.0.0",
        maturity="experimental",
        extends=["base"],
        languages=langs,
        language_layout=lang_layout,
        layout=LayoutProfileConfig(
            columns=config["columns"],
            spans_allowed=True,
            reading_order="parallel" if lang_layout == "parallel_columns" else "columns_ltr",
            orientation_policy=config["orientation"],
        ),
        numbering=NumberingProfileConfig(
            patterns=num_patterns,
            sections=["PHYSICS", "CHEMISTRY", "MATHEMATICS", "BIOLOGY"],
        ),
        options=OptionsProfileConfig(
            label_schemes=label_schemes,
            count_min=2,
            count_max=4,
            count_typical=4,
        ),
        furniture_branding=FurnitureBrandingProfileConfig(
            headers=[r"EXAM\s*PAPER"],
            footers=[r"Page\s*\d+"],
            watermark=watermark_cfg,
        ),
        expected_kinds=[config["primary_kind"]],
        output=OutputProfileConfig(
            template="exam.html.j2",
            layout_mode="bilingual_columns" if lang_layout == "parallel_columns" else "single_column",
        ),
    )
    return profile


def export_universal_families(
    output_dir: Path | str = "tests/universal/families",
    seed: int = 42,
) -> list[Path]:
    """Generate covering array and export each profile as YAML."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    combos = generate_pairwise_covering_array(seed=seed)
    exported_files: list[Path] = []

    for i, combo in enumerate(combos):
        prof = build_profile_for_combination(i, combo)
        yaml_path = out_path / f"{prof.id}.yaml"
        # Export as clean YAML dictionary
        raw_dict = prof.model_dump(exclude_none=True, mode="json")
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw_dict, f, sort_keys=False)
        exported_files.append(yaml_path)

    return exported_files
