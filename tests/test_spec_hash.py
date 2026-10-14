"""Tests for spec hash calculation and checkpoint invalidation."""

from __future__ import annotations

from examforge.profiles.loader import loader
from examforge.spec import compute_spec_hash


def test_spec_hash_determinism():
    prof = loader.load("neet_ug")
    h1 = compute_spec_hash(
        engine_version="2.0.0",
        profile=prof,
        enabled_rules=["R01", "R02"],
        compute_tier="standard",
    )
    h2 = compute_spec_hash(
        engine_version="2.0.0",
        profile=prof,
        enabled_rules=["R01", "R02"],
        compute_tier="standard",
    )
    assert h1 == h2
    assert len(h1) == 16


def test_spec_hash_changes_on_profile_change():
    prof1 = loader.load("neet_ug")
    prof2 = loader.load("jee_main")

    h1 = compute_spec_hash("2.0.0", prof1, ["R01"], "standard")
    h2 = compute_spec_hash("2.0.0", prof2, ["R01"], "standard")
    assert h1 != h2


def test_spec_hash_changes_on_rules_change():
    prof = loader.load("neet_ug")
    h1 = compute_spec_hash("2.0.0", prof, ["R01"], "standard")
    h2 = compute_spec_hash("2.0.0", prof, ["R01", "R02"], "standard")
    assert h1 != h2


def test_spec_hash_changes_on_compute_tier_change():
    prof = loader.load("neet_ug")
    h1 = compute_spec_hash("2.0.0", prof, ["R01"], "standard")
    h2 = compute_spec_hash("2.0.0", prof, ["R01"], "lite")
    assert h1 != h2


def test_spec_hash_changes_on_engine_version_change():
    prof = loader.load("neet_ug")
    h1 = compute_spec_hash("2.0.0", prof, ["R01"], "standard")
    h2 = compute_spec_hash("2.1.0", prof, ["R01"], "standard")
    assert h1 != h2
