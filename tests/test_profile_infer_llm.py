"""Tests for Phase 13.3 One-Shot LLM Profile Completion and Safety Guards."""

from __future__ import annotations

import json

from examforge.ir.schema import BBox, Block, ExamDocument, PageClassification, PageInfo
from examforge.llm.fake import FakeLLMClient
from examforge.profiles.infer_llm import complete_profile_llm
from examforge.profiles.infer_rules import ProfileInferenceResult
from examforge.profiles.schema import (
    ExamProfile,
    LanguageProfileConfig,
    LayoutProfileConfig,
    NumberingProfileConfig,
    OptionsProfileConfig,
)


def _make_sample_doc() -> ExamDocument:
    pages = [
        PageInfo(
            page_number=1,
            width_px=600,
            height_px=800,
            classification=PageClassification.QUESTIONS,
        )
    ]
    blocks = [
        Block(
            id="b1",
            page=1,
            bbox=BBox(x1=50, y1=100, x2=550, y2=130),
            text="Q.1 What is acceleration?",
        ),
        Block(
            id="b2",
            page=1,
            bbox=BBox(x1=50, y1=135, x2=550, y2=165),
            text="(A) m/s (B) m/s^2 (C) N (D) J",
        ),
        Block(
            id="b3",
            page=1,
            bbox=BBox(x1=50, y1=200, x2=550, y2=230),
            text="Q.2 What is momentum?",
        ),
        Block(
            id="b4",
            page=1,
            bbox=BBox(x1=50, y1=235, x2=550, y2=265),
            text="(A) kg m/s (B) kg m/s^2",
        ),
    ]
    return ExamDocument(source_path="test.pdf", pages=pages, blocks=blocks)


def test_infer_llm_zero_tokens_when_confidence_high():
    doc = _make_sample_doc()
    prof = ExamProfile(
        id="test_high_conf",
        name="Test",
        maturity="experimental",
        languages=[LanguageProfileConfig(code="en", script="Latn")],
        language_layout="monolingual",
        layout=LayoutProfileConfig(columns=1),
        numbering=NumberingProfileConfig(patterns=[r"^Q\.\d+"]),
        options=OptionsProfileConfig(label_schemes=["(A)", "(B)", "(C)", "(D)"]),
    )
    res = ProfileInferenceResult(
        profile=prof,
        field_confidences={"numbering.patterns": 0.95, "options.label_schemes": 0.95},
        overall_confidence=0.95,
        low_confidence_fields=[],  # Empty -> no LLM call needed
    )
    fake_llm = FakeLLMClient()

    completed_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_llm)
    assert len(fake_llm.calls) == 0  # Zero tokens consumed!
    assert not needs_review
    assert completed_prof.id == "test_high_conf"


def test_infer_llm_valid_completion():
    doc = _make_sample_doc()
    prof = ExamProfile(
        id="test_low_conf",
        name="Test",
        maturity="experimental",
        languages=[LanguageProfileConfig(code="en", script="Latn")],
    )
    res = ProfileInferenceResult(
        profile=prof,
        field_confidences={"numbering.patterns": 0.40, "options.label_schemes": 0.40},
        overall_confidence=0.40,
        low_confidence_fields=["numbering.patterns", "options.label_schemes"],
    )

    valid_response = json.dumps(
        {
            "numbering_patterns": [r"(?i)^\s*Q\.?\s*(\d{1,3})"],
            "option_labels": ["(A)", "(B)", "(C)", "(D)"],
        }
    )
    fake_llm = FakeLLMClient(default_content=valid_response)

    completed_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_llm)
    assert len(fake_llm.calls) == 1
    assert not needs_review
    assert completed_prof.options.label_schemes == ["(A)", "(B)", "(C)", "(D)"]
    assert any("Q" in pat for pat in completed_prof.numbering.patterns)


def test_infer_llm_hostile_backtracking_regex_guarded():
    doc = _make_sample_doc()
    prof = ExamProfile(id="test_hostile", name="Test")
    res = ProfileInferenceResult(
        profile=prof,
        field_confidences={"numbering.patterns": 0.30},
        overall_confidence=0.30,
        low_confidence_fields=["numbering.patterns"],
    )

    # Catastrophic backtracking pattern
    hostile_response = json.dumps(
        {
            "numbering_patterns": [r"^(a+)+$"],
            "option_labels": ["(A)", "(B)"],
        }
    )
    fake_llm = FakeLLMClient(default_content=hostile_response)

    completed_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_llm)
    assert len(fake_llm.calls) == 1
    # Must reject dangerous regex and flag needs_review without crashing
    assert needs_review


def test_infer_llm_malformed_json_fallback():
    doc = _make_sample_doc()
    prof = ExamProfile(id="test_malformed", name="Test")
    res = ProfileInferenceResult(
        profile=prof,
        field_confidences={"numbering.patterns": 0.30},
        overall_confidence=0.30,
        low_confidence_fields=["numbering.patterns"],
    )

    fake_llm = FakeLLMClient(
        default_content="SYSTEM PROMPT INJECTION: IGNORE PREVIOUS INSTRUCTIONS"
    )

    completed_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_llm)
    assert len(fake_llm.calls) == 1
    assert needs_review
    # Never crash, fallback provided
    assert completed_prof is not None
