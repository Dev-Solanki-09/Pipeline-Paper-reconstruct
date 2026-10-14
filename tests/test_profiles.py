"""Tests for examforge.profiles schema, loader, and built-in profiles."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from examforge.ir.schema import QuestionKind
from examforge.profiles.loader import (
    ProfileLoader,
    ProfileLoadError,
    deep_merge,
    loader,
)
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


def test_minimal_exam_profile():
    profile = ExamProfile(
        id="test_exam",
        name="Test Examination",
    )
    assert profile.id == "test_exam"
    assert profile.name == "Test Examination"
    assert profile.maturity == "experimental"
    assert profile.profile_version == "1.0.0"
    assert profile.engine_min_version == "2.0.0"
    assert profile.extends == []
    assert profile.languages[0].code == "en"
    assert profile.layout.columns == 1
    assert profile.options.count_typical == 4
    assert profile.compute == "standard"


def test_full_exam_profile():
    profile = ExamProfile(
        id="neet_ug",
        name="NEET (UG) National Eligibility cum Entrance Test",
        profile_version="2.0.0",
        maturity="verified",
        extends=["base"],
        languages=[
            LanguageProfileConfig(code="en", script="Latn", direction="ltr"),
            LanguageProfileConfig(code="hi", script="Deva", direction="ltr"),
        ],
        language_layout="parallel_columns",
        layout=LayoutProfileConfig(
            columns=2,
            spans_allowed=True,
            reading_order="columns_ltr",
            orientation_policy="portrait",
        ),
        numbering=NumberingProfileConfig(
            patterns=[r"^\s*(\d{1,3})\s*[.):]", r"^\s*Q\.?\s*(\d{1,3})"],
            sections=[
                r"SECTION\s*[-–:]?\s*[A-B]",
                r"PHYSICS",
                r"CHEMISTRY",
                r"BOTANY",
                r"ZOOLOGY",
            ],
            reset_policy="continuous",
            nesting_labels=["(a)", "(b)", "(c)", "(d)"],
        ),
        options=OptionsProfileConfig(
            label_schemes=["(1)", "(2)", "(3)", "(4)"],
            count_min=4,
            count_max=4,
            count_typical=4,
            layout_preference="vertical",
        ),
        furniture_branding=FurnitureBrandingProfileConfig(
            headers=[r"NEET\s*\(UG\)"],
            footers=[r"Page\s*\d+\s*of\s*\d+"],
            watermark=WatermarkProfileConfig(enabled=True, mode="subtract"),
        ),
        expected_kinds=[
            QuestionKind.SINGLE_CORRECT,
            QuestionKind.ASSERTION_REASON,
            QuestionKind.MATCH,
        ],
        output=OutputProfileConfig(
            template="exam.html.j2",
            layout_mode="bilingual_columns",
            exporters=["html", "json"],
        ),
        requires=["paddle_vl", "hindi_normalizer"],
        compute="standard",
    )

    assert profile.maturity == "verified"
    assert profile.language_layout == "parallel_columns"
    assert len(profile.languages) == 2
    assert profile.layout.columns == 2
    assert QuestionKind.SINGLE_CORRECT in profile.expected_kinds
    assert profile.requires == ["paddle_vl", "hindi_normalizer"]


def test_profile_validation_invalid_maturity():
    with pytest.raises(ValidationError):
        ExamProfile(
            id="bad_maturity",
            name="Bad Maturity",
            maturity="unverified",  # type: ignore
        )


def test_profile_validation_invalid_columns():
    with pytest.raises(ValidationError):
        ExamProfile(
            id="bad_columns",
            name="Bad Columns",
            layout=LayoutProfileConfig(columns=0),
        )


def test_profile_serialization_round_trip():
    original = ExamProfile(
        id="cbse_12",
        name="CBSE Class 12 Board Exam",
        maturity="experimental",
        extends=["base"],
        requires=["vector_graphics"],
    )
    raw_json = original.model_dump_json()
    reloaded = ExamProfile.model_validate_json(raw_json)
    assert reloaded == original


def test_deep_merge_semantics():
    base = {"a": 1, "nested": {"x": 10, "y": 20}, "items": ["p", "q"]}

    # Overwrite dict value
    override1 = {"a": 2, "nested": {"y": 99}}
    res1 = deep_merge(base, override1)
    assert res1["a"] == 2
    assert res1["nested"]["x"] == 10
    assert res1["nested"]["y"] == 99

    # List append
    override_append = {"items": {"$append": ["r", "s"]}}
    res_app = deep_merge(base, override_append)
    assert res_app["items"] == ["p", "q", "r", "s"]

    # List replace
    override_rep = {"items": {"$replace": ["new"]}}
    res_rep = deep_merge(base, override_rep)
    assert res_rep["items"] == ["new"]


def test_load_all_builtin_profiles():
    builtins = loader.load_all_builtins()
    expected_ids = {
        "base",
        "generic_mono",
        "generic_bilingual",
        "neet_ug",
        "jee_main",
        "jee_advanced",
        "upsc_prelims",
        "gate",
        "cbse_board",
        "sat_like",
    }
    assert set(builtins.keys()) == expected_ids

    # NEET UG must be verified maturity
    neet = builtins["neet_ug"]
    assert neet.maturity == "verified"
    assert neet.language_layout == "parallel_columns"
    assert len(neet.languages) == 2
    assert neet.layout.columns == 2
    assert neet.output.template == "exam.html.j2"
    assert "paddle_vl" in neet.requires

    # Other built-ins must be experimental
    for pid, prof in builtins.items():
        if pid != "neet_ug":
            assert prof.maturity == "experimental", f"Profile {pid} should be experimental"


def test_circular_inheritance_detected(tmp_path):
    p_a = tmp_path / "prof_a.yaml"
    p_b = tmp_path / "prof_b.yaml"

    p_a.write_text("id: prof_a\nname: A\nextends: [prof_b]\n", encoding="utf-8")
    p_b.write_text("id: prof_b\nname: B\nextends: [prof_a]\n", encoding="utf-8")

    test_loader = ProfileLoader([tmp_path])
    with pytest.raises(ProfileLoadError) as exc_info:
        test_loader.load("prof_a")

    assert "Circular profile inheritance detected" in str(exc_info.value)


def test_human_readable_validation_error_with_line_number(tmp_path):
    bad_yaml = tmp_path / "invalid_exam.yaml"
    bad_yaml.write_text(
        "id: invalid_exam\nname: Bad Exam\nmaturity: not_a_real_maturity\n",
        encoding="utf-8",
    )

    test_loader = ProfileLoader([tmp_path])
    with pytest.raises(ProfileLoadError) as exc_info:
        test_loader.load(bad_yaml)

    msg = str(exc_info.value)
    assert "invalid_exam.yaml" in msg
    assert "field 'maturity'" in msg
