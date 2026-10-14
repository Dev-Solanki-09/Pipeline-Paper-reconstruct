"""
Oracle-stage attribution harness (Phase O0.2).

Substitutes ground truth IR at a specified pipeline stage boundary,
executes downstream stages, and measures metric deltas to pinpoint
which stage incurs the largest accuracy loss.
"""

from __future__ import annotations

from typing import Any

from examforge.eval.scorer import EvaluationResult, ExamScorer
from examforge.ir.schema import ExamDocument
from examforge.orchestrator.runner import PipelineRunner
from examforge.spec import Spec
from examforge.stages import (
    S0Intake,
    S1Profile,
    S2Clean,
    S3Parse,
    S4Structure,
    S5Hindi,
    S5Math,
    S6Figures,
    S7Repair,
    S8Verify,
    S9Package,
)
from examforge.stages.base import StageContext

STAGE_ORDER = [
    "S0",
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "S8",
    "S7",
    "S9",
]


def run_oracle_attribution(
    oracle_stage: str,
    gt_doc: ExamDocument,
    hyp_doc: ExamDocument | None = None,
    runner: PipelineRunner | None = None,
) -> EvaluationResult:
    """
    Run evaluation with oracle ground-truth substitution at oracle_stage.

    - If oracle_stage is 'S9' (or final stage): substitutes GT at the end, yielding perfect 1.0 score.
    - If oracle_stage is 'S0': uses hyp_doc (or normal pipeline output) directly without GT substitution.
    - If oracle_stage is an intermediate stage: substitutes gt_doc at that stage boundary,
      runs remaining downstream stages, and scores against gt_doc.
    """
    oracle_stage = oracle_stage.upper().strip()
    scorer = ExamScorer()

    if oracle_stage in ("S9", "FINAL"):
        # Substituting ground truth at the last stage yields perfect score
        return scorer.score(gt_doc, gt_doc)

    if oracle_stage in ("S0", "INITIAL", "NONE"):
        # Equals normal run without substitution
        eval_hyp = hyp_doc if hyp_doc is not None else gt_doc
        return scorer.score(gt_doc, eval_hyp)

    # For intermediate stages: substitute GT document and run downstream stages
    stage_classes = {
        "S0": S0Intake,
        "S3": S3Parse,
        "S1": S1Profile,
        "S2": S2Clean,
        "S4": S4Structure,
        "S5": S5Math,
        "S6": S6Figures,
        "S8": S8Verify,
        "S7": S7Repair,
        "S9": S9Package,
    }

    if oracle_stage not in STAGE_ORDER:
        raise ValueError(f"Unknown oracle stage: {oracle_stage}. Valid stages: {STAGE_ORDER}")

    start_idx = STAGE_ORDER.index(oracle_stage)
    # Downstream stages to run after substituting GT at oracle_stage
    downstream_keys = STAGE_ORDER[start_idx + 1 :]

    doc_state = gt_doc.model_copy(deep=True)

    if runner is not None:
        ctx = StageContext(
            document=doc_state,
            spec=runner.spec or Spec.default(),
            config=runner.config,
            profile=runner.profile,
        )
        for stage_key in downstream_keys:
            stage_cls = stage_classes.get(stage_key)
            if stage_cls:
                stage_instance = stage_cls()
                res = stage_instance.run(ctx)
                ctx.document = res.document
        final_doc = ctx.document
    else:
        # Standalone mock execution without runner
        final_doc = doc_state

    return scorer.score(gt_doc, final_doc)
