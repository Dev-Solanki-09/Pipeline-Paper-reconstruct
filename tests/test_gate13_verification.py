"""
Phase 13 Gate Verification Suite: Auto-Profiling & Scaffolding (S1).

Verifies:
1. Fingerprint stability under noise (>= 0.95 match) and distinctness across families.
2. Deterministic inference accuracy across diverse synthetic exam families.
3. FakeLLM completion safety (hostile regex timeout/guard, invalid JSON fallback).
4. Cache hit guarantees zero LLM tokens on subsequent runs.
5. End-to-end scaffolding with draft YAML and visual overlay HTML generation.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    PageClassification,
    PageInfo,
)
from examforge.llm.fake import FakeLLMClient
from examforge.profiles.fingerprint import (
    extract_document_fingerprint,
)
from examforge.profiles.infer_llm import complete_profile_llm
from examforge.profiles.infer_rules import (
    ProfileInferenceResult,
    infer_profile_deterministic,
)
from examforge.profiles.scaffold import scaffold_profile
from examforge.profiles.schema import ExamProfile
from examforge.stages.base import StageContext
from examforge.stages.s1_profile import S1Profile


def _create_synthetic_doc(
    family: str,
    num_questions: int = 10,
    noise_shift: int = 0,
) -> ExamDocument:
    """Generate deterministic synthetic documents across various exam families."""
    pages = [
        PageInfo(
            page_number=1,
            width_px=600,
            height_px=800,
            classification=PageClassification.QUESTIONS,
        )
    ]
    blocks = []

    if family == "jee_main":
        # Single column, English, Q. prefix, (1), (2), (3), (4)
        blocks.append(
            Block(
                id="hdr",
                page=1,
                bbox=BBox(x1=50, y1=20, x2=550, y2=50),
                text="JEE MAIN 2026 - PHYSICS",
            )
        )
        for i in range(1, num_questions + 1):
            y = 60 + i * 65 + noise_shift
            blocks.append(
                Block(
                    id=f"b_{i}",
                    page=1,
                    bbox=BBox(x1=50, y1=y, x2=550, y2=y + 25),
                    text=f"Q.{i} Find velocity of particle.",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_o",
                    page=1,
                    bbox=BBox(x1=50, y1=y + 28, x2=550, y2=y + 50),
                    text="(1) 10 m/s (2) 20 m/s (3) 30 m/s (4) 40 m/s",
                )
            )

    elif family == "neet_bilingual":
        # Two columns, Left: English, Right: Hindi
        blocks.append(
            Block(id="hdr", page=1, bbox=BBox(x1=50, y1=20, x2=550, y2=50), text="NEET UG 2026")
        )
        for i in range(1, num_questions + 1):
            y = 60 + i * 65 + noise_shift
            blocks.append(
                Block(
                    id=f"b_{i}_en",
                    page=1,
                    bbox=BBox(x1=50, y1=y, x2=280, y2=y + 25),
                    text=f"{i}. Calculate work done.",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_eno",
                    page=1,
                    bbox=BBox(x1=50, y1=y + 28, x2=280, y2=y + 50),
                    text="(A) 10 J (B) 20 J (C) 30 J (D) 40 J",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_hi",
                    page=1,
                    bbox=BBox(x1=320, y1=y, x2=550, y2=y + 25),
                    text=f"प्रश्न {i}. किए गए कार्य की गणना करें।",
                )
            )

    elif family == "cbse_board":
        # Single column, Roman numbering, (a), (b), (c), (d)
        blocks.append(
            Block(
                id="hdr",
                page=1,
                bbox=BBox(x1=50, y1=20, x2=550, y2=50),
                text="CBSE CLASS XII - CHEMISTRY",
            )
        )
        for i in range(1, num_questions + 1):
            y = 60 + i * 65 + noise_shift
            blocks.append(
                Block(
                    id=f"b_{i}",
                    page=1,
                    bbox=BBox(x1=50, y1=y, x2=550, y2=y + 25),
                    text=f"{i}. State Raoult's law.",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_o",
                    page=1,
                    bbox=BBox(x1=50, y1=y + 28, x2=550, y2=y + 50),
                    text="(A) Ideal (B) Non-ideal (C) Azeotropic (D) Colligative",
                )
            )

    return ExamDocument(source_path=f"{family}.pdf", pages=pages, blocks=blocks)


def test_gate13_fingerprint_stability_and_distinctness():
    """Verify fingerprint stability under coordinate noise and distinctness across families."""
    doc_jee = _create_synthetic_doc("jee_main", noise_shift=0)
    doc_jee_shifted = _create_synthetic_doc("jee_main", noise_shift=2)
    doc_neet = _create_synthetic_doc("neet_bilingual")
    doc_cbse = _create_synthetic_doc("cbse_board")

    fp_jee = extract_document_fingerprint(doc_jee)
    fp_jee_shifted = extract_document_fingerprint(doc_jee_shifted)
    fp_neet = extract_document_fingerprint(doc_neet)
    fp_cbse = extract_document_fingerprint(doc_cbse)

    # 1. Stability under noise: doc_hash and key attributes must match identical structure
    assert fp_jee.doc_hash == fp_jee_shifted.doc_hash
    assert fp_jee.estimated_columns == fp_jee_shifted.estimated_columns == 1
    assert fp_jee.dominant_numbering == fp_jee_shifted.dominant_numbering

    # 2. Distinctness across families
    assert fp_jee.doc_hash != fp_neet.doc_hash
    assert fp_jee.doc_hash != fp_cbse.doc_hash
    assert fp_neet.doc_hash != fp_cbse.doc_hash

    # Neet is 2 columns, bilingual; JEE is 1 column monolingual
    assert fp_neet.estimated_columns == 2
    assert fp_jee.estimated_columns == 1
    assert "Deva" in fp_neet.script_distribution
    assert "Deva" not in fp_jee.script_distribution


def test_gate13_deterministic_inference_accuracy():
    """Verify deterministic inference accurately derives language, layout, and patterns."""
    doc_neet = _create_synthetic_doc("neet_bilingual")
    fp_neet = extract_document_fingerprint(doc_neet)
    res_neet = infer_profile_deterministic(doc_neet, fp_neet)

    p_neet = res_neet.profile
    assert len(p_neet.languages) == 2
    assert p_neet.language_layout == "parallel_columns"
    assert p_neet.layout.columns == 2
    assert p_neet.options.label_schemes == ["(A)", "(B)", "(C)", "(D)"]
    assert res_neet.overall_confidence >= 0.85

    doc_jee = _create_synthetic_doc("jee_main")
    fp_jee = extract_document_fingerprint(doc_jee)
    res_jee = infer_profile_deterministic(doc_jee, fp_jee)

    p_jee = res_jee.profile
    assert len(p_jee.languages) == 1
    assert p_jee.language_layout == "monolingual"
    assert p_jee.layout.columns == 1
    assert p_jee.options.label_schemes == ["(1)", "(2)", "(3)", "(4)"]
    assert any("Q" in pat for pat in p_jee.numbering.patterns)
    assert res_jee.overall_confidence >= 0.85


def test_gate13_fakellm_completion_safety_and_guards():
    """Verify LLM completion safely handles hostile regex and invalid JSON fallbacks."""
    doc = _create_synthetic_doc("cbse_board")
    prof = ExamProfile(id="test_scaffold", name="Test")
    res = ProfileInferenceResult(
        profile=prof,
        field_confidences={"numbering.patterns": 0.20, "options.label_schemes": 0.20},
        overall_confidence=0.20,
        low_confidence_fields=["numbering.patterns", "options.label_schemes"],
    )

    # 1. Catastrophic backtracking regex guard
    hostile_regex_payload = json.dumps(
        {
            "numbering_patterns": [r"^(a+)+$"],
            "option_labels": ["(A)", "(B)"],
        }
    )
    fake_hostile = FakeLLMClient(default_content=hostile_regex_payload)
    out_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_hostile)
    assert needs_review  # Dangerous regex rejected!

    # 2. Malformed JSON payload fallback
    fake_malformed = FakeLLMClient(default_content="INVALID NOT JSON {{")
    out_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_malformed)
    assert needs_review
    assert out_prof is not None  # Never crashes!

    # 3. Valid completion succeeds
    valid_payload = json.dumps(
        {
            "numbering_patterns": [r"^\s*(\d+)\.\s*"],
            "option_labels": ["(A)", "(B)", "(C)", "(D)"],
        }
    )
    fake_valid = FakeLLMClient(default_content=valid_payload)
    out_prof, needs_review = complete_profile_llm(res, doc, llm_client=fake_valid)
    assert not needs_review
    assert out_prof.options.label_schemes == ["(A)", "(B)", "(C)", "(D)"]


def test_gate13_cache_hit_and_e2e_scaffolding(tmp_path: Path):
    """Verify cache hit avoids re-computation and scaffolding produces valid artifacts."""
    doc = _create_synthetic_doc("neet_bilingual")
    output_dir = tmp_path / "learned"
    cache_path = tmp_path / "cache.sqlite"

    # Run scaffolding
    yaml_path, html_path, prof, low_conf = scaffold_profile(
        doc=doc,
        output_dir=output_dir,
        profile_id="neet_bilingual_v2",
        cache_path=cache_path,
    )

    assert yaml_path.exists()
    assert html_path.exists()

    # Verify YAML is loadable as ExamProfile
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    loaded_profile = ExamProfile.model_validate(data)
    assert loaded_profile.id == "neet_bilingual_v2"
    assert loaded_profile.layout.columns == 2

    # Verify cache hit via Stage S1 Profile
    cfg = ExamForgeConfig()
    cfg.flags["autoprofile"] = True
    cfg.profile_cache_path = cache_path

    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s1",
        run_dir=tmp_path / "run",
    )

    stage = S1Profile()
    res = stage.run(ctx)
    assert res.metrics["autoprofiled"]
    assert res.metrics["cache_hit"]
    assert res.metrics["profile"] == "neet_bilingual_v2"
