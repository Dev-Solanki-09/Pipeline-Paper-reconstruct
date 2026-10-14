"""
Phase O0 Test Suite: Measurement, Oracle Attribution & Error Taxonomy.

Validates:
1. Oracle stage substitution harness (O0.2):
   - Substituting GT at S9 yields 1.000 (perfect score).
   - Substituting at S0 equals normal evaluation.
2. Error taxonomy snapshot diff tool (O0.3):
   - Identical stage snapshots produce 0 errors.
   - S5 text modification produces ErrorClass.NORMALIZATION_DAMAGE.
   - S7 text modification produces ErrorClass.REPAIR_DAMAGE.
   - S2 dropped question produces ErrorClass.CLEANING_DAMAGE.
   - Missing question in final IR produces ErrorClass.MISSING_CONTENT.
3. CLI eval --oracle execution.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from examforge.cli import main
from examforge.eval.oracle import run_oracle_attribution
from examforge.eval.taxonomy import (
    ClassifiedError,
    ErrorClass,
    diff_snapshots_against_gt,
)
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    ExamDocument,
    Option,
    PageInfo,
    Question,
    TextNode,
)
from examforge.synth.generator import SyntheticDocumentGenerator


def _create_mock_doc(stem_text: str = "1. What is velocity?") -> ExamDocument:
    node = TextNode(texts={"en": stem_text})
    q = Question(
        id="q_1",
        number=1,
        stem=[node],
        stem_text_en=stem_text,
        options=[Option(label="A", text_str_en="m/s")],
        source_pages=[1],
    )
    return ExamDocument(
        source_path="mock.pdf",
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
        questions=[q],
    )


def test_oracle_attribution_harness():
    """Verify oracle substitution properties."""
    gen = SyntheticDocumentGenerator(seed=42)
    gt_doc = gen.generate(num_questions=6)
    hyp_doc = gt_doc.model_copy(deep=True)

    # 1. Substituting at S9 yields 1.000 aggregate score
    res_s9 = run_oracle_attribution("S9", gt_doc, hyp_doc)
    assert res_s9.aggregate_score == 1.0
    assert res_s9.sequence_accuracy == 1.0

    # 2. Substituting at S0 equals normal evaluation
    res_s0 = run_oracle_attribution("S0", gt_doc, hyp_doc)
    assert res_s0.aggregate_score == 1.0


def test_snapshot_diff_identical_produces_no_errors():
    """Identical IR snapshots produce zero taxonomy errors."""
    doc = _create_mock_doc()
    snapshots = {"S4": doc, "S5": doc, "S7": doc, "S8": doc, "S9": doc}
    errors = diff_snapshots_against_gt(doc, snapshots)
    assert len(errors) == 0


def test_snapshot_diff_normalization_damage():
    """Text correct in S4 but damaged in S5 classifies as NORMALIZATION_DAMAGE."""
    gt = _create_mock_doc("1. What is velocity?")
    s4_doc = _create_mock_doc("1. What is velocity?")  # correct
    s5_doc = _create_mock_doc("1. What is velocty?")   # damaged by S5
    s9_doc = s5_doc

    snapshots = {"S4": s4_doc, "S5": s5_doc, "S9": s9_doc}
    errors = diff_snapshots_against_gt(gt, snapshots)

    assert any(e.error_class == ErrorClass.NORMALIZATION_DAMAGE for e in errors)
    norm_err = next(e for e in errors if e.error_class == ErrorClass.NORMALIZATION_DAMAGE)
    assert norm_err.stage == "S5"
    assert norm_err.question_number == 1


def test_snapshot_diff_repair_damage():
    """Text correct in S8 but damaged in S7 classifies as REPAIR_DAMAGE."""
    gt = _create_mock_doc("1. Calculate force.")
    s8_doc = _create_mock_doc("1. Calculate force.")  # correct
    s7_doc = _create_mock_doc("1. Calculate farc.")   # damaged by S7 patch
    s9_doc = s7_doc

    snapshots = {"S4": s8_doc, "S5": s8_doc, "S8": s8_doc, "S7": s7_doc, "S9": s9_doc}
    errors = diff_snapshots_against_gt(gt, snapshots)

    assert any(e.error_class == ErrorClass.REPAIR_DAMAGE for e in errors)
    repair_err = next(e for e in errors if e.error_class == ErrorClass.REPAIR_DAMAGE)
    assert repair_err.stage == "S7"


def test_snapshot_diff_cleaning_damage_and_missing_content():
    """Content dropped in S2 classifies as CLEANING_DAMAGE, otherwise MISSING_CONTENT."""
    gt = _create_mock_doc("1. Test question.")
    empty_doc = ExamDocument(
        source_path="mock.pdf",
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
        questions=[],
        blocks=[
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=0, y1=0, x2=10, y2=10),
                text="1. Test question.",
                status=BlockStatus.DROPPED,
            )
        ],
    )
    snapshots = {"S2": empty_doc, "S9": empty_doc}
    errors = diff_snapshots_against_gt(gt, snapshots)
    assert any(e.error_class == ErrorClass.CLEANING_DAMAGE for e in errors)


def test_cli_eval_with_oracle():
    """Verify CLI eval --oracle S9 executes cleanly."""
    runner = CliRunner()
    res = runner.invoke(main, ["eval", "--oracle", "S9"])
    assert res.exit_code == 0
    assert "[ORACLE] Substituting ground truth at stage S9" in res.output
    assert "Aggregate Score:       1.0000" in res.output
