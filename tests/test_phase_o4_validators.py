"""
Tests for Phase O4: Validator Consolidation and Cost Tiers.

Verifies:
- O4.1: Cost Tiers (Free, IO, Heavy) declared on all validators and respected by S8Verify.
- O4.2: Consolidated rules:
  - furniture_branding (R01 + R02)
  - language_consistency (R05 + R10)
  - structure_integrity (R06 + R14 + R15)
  - packaged_output_check (R04 + R13)
  - Legacy check names resolve seamlessly via aliases.
- O4.3: Incremental verification via verify_question() scoped only to target question.
- O4.4: WARN issues never trigger repair (BLOCKER gating in S7).
- O4.5: Capability / profile gating skips bilingual checks on monolingual documents.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureNode,
    Issue,
    IssueSeverity,
    Lang,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
    TextNode,
)
from examforge.spec import Rule, RuleSeverity, Spec
from examforge.stages.base import StageContext
from examforge.stages.s7_repair import S7Repair
from examforge.stages.s8_verify import S8Verify, verify_question
from examforge.validators import (
    CostTier,
    furniture_branding,
    get_canonical_validator_name,
    get_validator,
    get_validator_tier,
    language_consistency,
    packaged_output_check,
    structure_integrity,
)


def test_o4_1_cost_tiers_assigned_and_gated(tmp_path: Path):
    """Verify all validators have declared CostTiers and S8Verify respects allowed_cost_tiers."""
    # Check cost tier assignments
    assert get_validator_tier("furniture_branding") == CostTier.FREE
    assert get_validator_tier("language_consistency") == CostTier.FREE
    assert get_validator_tier("structure_integrity") == CostTier.FREE
    assert get_validator_tier("formula_roundtrip") == CostTier.FREE
    assert get_validator_tier("watermark_residual") == CostTier.IO
    assert get_validator_tier("figure_clean_border_and_present") == CostTier.IO
    assert get_validator_tier("text_layer_agreement") == CostTier.IO
    assert get_validator_tier("packaged_output_check") == CostTier.HEAVY
    assert get_validator_tier("render_check") == CostTier.HEAVY

    # Create document with a flaw detected by a FREE validator and an IO validator
    doc = ExamDocument(
        schema_version=2,
        source_path="test.pdf",
        source_hash="h1",
        metadata=ExamMetadata(exam_name="Tier Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700, classification=PageClassification.QUESTIONS)],
        blocks=[
            Block(
                id="b1",
                page=1,
                type=BlockType.HEADER,
                bbox=BBox(x1=10, y1=10, x2=100, y2=20),
                text="CONFIDENTIAL TEST BOOKLET",  # Triggers FREE furniture_branding
                status=BlockStatus.TRUSTED,
            )
        ],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="As shown in the given below figure, find current.",  # Triggers IO figure_clean_border_and_present
                options=[Option(label="A", text_str_en="1 A"), Option(label="B", text_str_en="2 A")],
            )
        ],
    )

    stage = S8Verify()
    ctx = StageContext(
        document=doc,
        run_dir=tmp_path,
        config=None,
        spec=Spec.default(verifiers_v2=True),
        stage_dir=tmp_path / "s8",
    )

    # 1. Run with only FREE tier
    res_free = stage.run(ctx, allowed_cost_tiers={CostTier.FREE})
    free_rules = {i.rule for i in res_free.issues}
    assert "furniture_branding" in free_rules or "no_headers_footers_page_numbers" in free_rules
    assert "figure_clean_border_and_present" not in free_rules
    assert res_free.metrics["tiers_skipped"] > 0

    # 2. Run with FREE + IO tiers
    doc_io = doc.model_copy(update={"issues": []})
    ctx_io = StageContext(
        document=doc_io,
        run_dir=tmp_path,
        config=None,
        spec=Spec.default(verifiers_v2=True),
        stage_dir=tmp_path / "s8",
    )
    res_io = stage.run(ctx_io, allowed_cost_tiers={CostTier.FREE, CostTier.IO})
    io_rules = {i.rule for i in res_io.issues}
    assert "figure_clean_border_and_present" in io_rules


def test_o4_2_merged_overlapping_rules():
    """Verify consolidation of rules and transparent alias lookup."""
    # Aliases resolve to canonical names
    assert get_canonical_validator_name("no_headers_footers_page_numbers") == "furniture_branding"
    assert get_canonical_validator_name("no_brand_text_or_logo") == "furniture_branding"
    assert get_canonical_validator_name("en_hi_pairs_complete") == "language_consistency"
    assert get_canonical_validator_name("numbering_continuity") == "structure_integrity"
    assert get_canonical_validator_name("sequence_gaps") == "structure_integrity"
    assert get_canonical_validator_name("structure_consistency") == "structure_integrity"
    assert get_canonical_validator_name("no_page_wrappers_or_breaks") == "packaged_output_check"
    assert get_canonical_validator_name("render_check") == "packaged_output_check"

    # Validators retrieved by legacy or canonical names return functional callable
    assert callable(get_validator("no_headers_footers_page_numbers"))
    assert callable(get_validator("furniture_branding"))
    assert callable(get_validator("sequence_gaps"))
    assert callable(get_validator("structure_integrity"))
    assert callable(get_validator("render_check"))
    assert callable(get_validator("packaged_output_check"))


def test_o4_3_incremental_verify():
    """Verify verify_question runs scoped verification only on target question."""
    q1 = Question(
        id="q1",
        number=1,
        stem_text_en="Question 1 text",
        options=[Option(label="A", text_str_en="10"), Option(label="B", text_str_en="20")],
    )
    q2 = Question(
        id="q2",
        number=2,
        kind=QuestionKind.SINGLE_CORRECT,
        stem_text_en="MCQ Question 2 with no options",  # Structural error on Q2
        options=[],
    )

    doc = ExamDocument(
        schema_version=2,
        source_path="dummy.pdf",
        source_hash="h1",
        metadata=ExamMetadata(exam_name="Incremental Test"),
        questions=[q1, q2],
    )

    # Verifying q1 should produce zero issues
    issues_q1 = verify_question(doc, "q1")
    assert len(issues_q1) == 0

    # Verifying q2 should flag q2's issue only
    issues_q2 = verify_question(doc, "q2")
    assert len(issues_q2) >= 1
    assert all(i.question_id == "q2" for i in issues_q2)


def test_o4_4_warn_never_triggers_repair(tmp_path: Path):
    """Verify S7 Repair skips WARN issues and only acts on BLOCKER issues."""
    doc = ExamDocument(
        schema_version=2,
        source_path="test.pdf",
        source_hash="h1",
        metadata=ExamMetadata(exam_name="Warn Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700, classification=PageClassification.QUESTIONS)],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="A question with warning",
                options=[Option(label="A", text_str_en="A"), Option(label="B", text_str_en="B")],
            )
        ],
        issues=[
            Issue(
                id="warn_issue_1",
                stage="s8_verify",
                severity=IssueSeverity.WARNING,
                rule="lexicon",
                question_id="q1",
                message="Minor warning issue",
            )
        ],
    )

    stage = S7Repair()
    # Mock config with s7_repair enabled
    class DummyConfig:
        def flag(self, name: str, default: bool = False) -> bool:
            return True if name == "s7_repair" else default

    ctx = StageContext(
        document=doc,
        run_dir=tmp_path,
        config=DummyConfig(),  # type: ignore
        spec=None,
        stage_dir=tmp_path / "s7",
    )

    result = stage.run(ctx)
    # Warning was not dispatched to repair, repaired_count remains 0
    assert result.metrics["repaired_count"] == 0
    assert len(result.issues) == 1
    assert result.issues[0].id == "warn_issue_1"


def test_o4_5_capability_gating_skips_bilingual_on_monolingual(tmp_path: Path):
    """Verify S8 skips language_consistency when document has no Hindi content."""
    doc = ExamDocument(
        schema_version=2,
        source_path="mono.pdf",
        source_hash="h_mono",
        metadata=ExamMetadata(exam_name="Mono Test"),
        pages=[PageInfo(page_number=1, width_px=500, height_px=700, classification=PageClassification.QUESTIONS)],
        blocks=[
            Block(
                id="b1",
                page=1,
                type=BlockType.TEXT,
                bbox=BBox(x1=10, y1=10, x2=100, y2=20),
                text="Pure English question text",
                lang=Lang.EN,
                status=BlockStatus.TRUSTED,
            )
        ],
        questions=[
            Question(
                id="q1",
                number=1,
                stem_text_en="Pure English question",
                options=[Option(label="A", text_str_en="A"), Option(label="B", text_str_en="B")],
            )
        ],
    )

    stage = S8Verify()
    ctx = StageContext(
        document=doc,
        run_dir=tmp_path,
        config=None,
        spec=Spec.default(verifiers_v2=True),
        stage_dir=tmp_path / "s8",
    )

    result = stage.run(ctx)
    fired_rules = {i.rule for i in result.issues}
    # Should not fire any bilingual missing language warning or token error
    assert "en_hi_pairs_complete" not in fired_rules
    assert "language_consistency" not in fired_rules
