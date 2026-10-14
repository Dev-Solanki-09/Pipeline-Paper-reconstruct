"""Tests for Universality Matrix pairwise covering generator."""

from __future__ import annotations

import itertools

import pytest

from examforge.profiles.loader import ProfileLoader
from examforge.synth.matrix import (
    AXES,
    export_universal_families,
    generate_pairwise_covering_array,
)


def test_pairwise_covering_array_covers_all_pairs():
    """Verify that every pair of values across different axes appears in the covering array."""
    test_cases = generate_pairwise_covering_array(seed=42)
    assert len(test_cases) >= 12

    # Check pairwise coverage
    axis_names = list(AXES.keys())
    for (a1, a2) in itertools.combinations(axis_names, 2):
        for v1 in AXES[a1]:
            for v2 in AXES[a2]:
                pair_found = any(tc[a1] == v1 and tc[a2] == v2 for tc in test_cases)
                assert pair_found, f"Pair ({a1}={v1}, {a2}={v2}) not covered in covering array"


def test_export_universal_families(tmp_path):
    """Generated family profile YAMLs must be valid ExamProfile files."""
    exported = export_universal_families(output_dir=tmp_path / "families", seed=42)
    assert len(exported) >= 12

    loader = ProfileLoader(search_paths=[tmp_path / "families"])
    for f in exported:
        prof_id = f.stem
        # Ensure profile loads and validates without error
        prof = loader.load(prof_id)
        assert prof.id == prof_id
        assert prof.maturity == "experimental"
        assert prof.layout.columns in [1, 2, 3]
