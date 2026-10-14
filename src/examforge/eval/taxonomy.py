"""
Error taxonomy classifier and stage snapshot diff tool (Phase O0.3).

Analyzes IR snapshots across pipeline stages (S0 through S9) against ground truth
to categorize errors into actionable root-cause buckets:
- ocr_misread: Text recognition discrepancy originating at S3 parse
- wrong_split_merge: Incorrect question numbering or boundary segmentation
- wrong_figure_option_association: Incorrect figure ref or option assignment
- normalization_damage: Content was correct after S4, but altered/corrupted in S5
- cleaning_damage: Content/blocks lost or dropped in S2 or S6
- repair_damage: Question was correct before S7, but corrupted by repair patch
- validator_false_positive: Issue raised on a question that matches GT
- missing_content: Question in GT entirely absent from extracted document
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from examforge.ir.schema import ExamDocument, Question


class ErrorClass(str, Enum):
    OCR_MISREAD = "ocr_misread"
    WRONG_SPLIT_MERGE = "wrong_split_merge"
    WRONG_FIGURE_OPTION_ASSOCIATION = "wrong_figure_option_association"
    NORMALIZATION_DAMAGE = "normalization_damage"
    CLEANING_DAMAGE = "cleaning_damage"
    REPAIR_DAMAGE = "repair_damage"
    VALIDATOR_FALSE_POSITIVE = "validator_false_positive"
    MISSING_CONTENT = "missing_content"


@dataclass
class ClassifiedError:
    error_class: ErrorClass
    question_number: int | None
    stage: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _get_q_text(q: Question) -> str:
    """Helper to extract normalized stem text for comparison."""
    if hasattr(q, "stem_text_en") and q.stem_text_en:
        return q.stem_text_en.strip()
    parts = []
    for node in getattr(q, "stem", []):
        if getattr(node, "kind", None) == "text":
            texts = getattr(node, "texts", {})
            parts.extend(texts.values())
    return " ".join(parts).strip()


def diff_snapshots_against_gt(
    gt_doc: ExamDocument,
    stage_snapshots: dict[str, ExamDocument],
) -> list[ClassifiedError]:
    """
    Diff stage snapshots against ground truth to categorize errors.

    stage_snapshots should be a dictionary mapping stage names (e.g. 'S2', 'S4', 'S5', 'S7', 'S8', 'S9')
    to the ExamDocument snapshot recorded immediately after that stage.
    """
    errors: list[ClassifiedError] = []
    gt_q_map = {q.number: q for q in gt_doc.questions}
    final_doc = stage_snapshots.get("S9") or stage_snapshots.get(list(stage_snapshots.keys())[-1]) if stage_snapshots else None

    if final_doc is None:
        return errors

    final_q_map = {q.number: q for q in final_doc.questions}

    # 1. Missing content check
    for q_num, gt_q in gt_q_map.items():
        if q_num not in final_q_map:
            # Check if dropped in S2 cleaning
            s2_doc = stage_snapshots.get("S2")
            if s2_doc and any(
                b.status.value == "dropped" and f"{q_num}" in b.text for b in getattr(s2_doc, "blocks", [])
            ):
                errors.append(
                    ClassifiedError(
                        error_class=ErrorClass.CLEANING_DAMAGE,
                        question_number=q_num,
                        stage="S2",
                        description=f"Question {q_num} content dropped during S2 cleaning",
                        evidence={"question_number": q_num},
                    )
                )
            else:
                errors.append(
                    ClassifiedError(
                        error_class=ErrorClass.MISSING_CONTENT,
                        question_number=q_num,
                        stage="S4",
                        description=f"Question {q_num} missing in final extracted IR",
                        evidence={"question_number": q_num},
                    )
                )

    # 2. Check each question in final document against snapshots
    for q_num, final_q in final_q_map.items():
        gt_q = gt_q_map.get(q_num)
        if not gt_q:
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.WRONG_SPLIT_MERGE,
                    question_number=q_num,
                    stage="S4",
                    description=f"Extraneous question {q_num} extracted not in GT",
                )
            )
            continue

        gt_text = _get_q_text(gt_q)
        final_text = _get_q_text(final_q)

        # 3. Figure association discrepancy
        gt_figs = [getattr(n, "figure_ref", "") for n in getattr(gt_q, "stem", []) if getattr(n, "kind", "") == "figure"]
        final_figs = [getattr(n, "figure_ref", "") for n in getattr(final_q, "stem", []) if getattr(n, "kind", "") == "figure"]
        if gt_figs != final_figs:
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.WRONG_FIGURE_OPTION_ASSOCIATION,
                    question_number=q_num,
                    stage="S6",
                    description=f"Figure association mismatch for Q{q_num}: expected {gt_figs}, got {final_figs}",
                    evidence={"expected": gt_figs, "got": final_figs},
                )
            )

        # If text matches GT, check for validator false positive
        if gt_text == final_text:
            continue

        # Text differed from GT. Determine which stage caused the difference:
        s4_doc = stage_snapshots.get("S4")
        s5_doc = stage_snapshots.get("S5")
        s7_doc = stage_snapshots.get("S7")
        s8_doc = stage_snapshots.get("S8")

        s4_q = next((q for q in getattr(s4_doc, "questions", []) if q.number == q_num), None) if s4_doc else None
        s5_q = next((q for q in getattr(s5_doc, "questions", []) if q.number == q_num), None) if s5_doc else None
        s8_q = next((q for q in getattr(s8_doc, "questions", []) if q.number == q_num), None) if s8_doc else None
        s7_q = next((q for q in getattr(s7_doc, "questions", []) if q.number == q_num), None) if s7_doc else None

        s4_text = _get_q_text(s4_q) if s4_q else ""
        s5_text = _get_q_text(s5_q) if s5_q else ""
        s8_text = _get_q_text(s8_q) if s8_q else ""
        s7_text = _get_q_text(s7_q) if s7_q else ""

        # Case A: Normalization damage (correct after S4, but altered in S5)
        if s4_q and s4_text == gt_text and s5_text != gt_text:
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.NORMALIZATION_DAMAGE,
                    question_number=q_num,
                    stage="S5",
                    description=f"Q{q_num} correct in S4 but damaged by S5 normalization",
                    evidence={"before": s4_text, "after": s5_text, "gt": gt_text},
                )
            )
        # Case B: Repair damage (correct in S8, but corrupted by S7 repair patch)
        elif s8_q and s8_text == gt_text and s7_text != gt_text:
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.REPAIR_DAMAGE,
                    question_number=q_num,
                    stage="S7",
                    description=f"Q{q_num} correct in S8 but damaged by S7 repair patch",
                    evidence={"before": s8_text, "after": s7_text, "gt": gt_text},
                )
            )
        # Case C: Cleaning damage (blocks lost in S2)
        elif s4_doc and len(getattr(s4_q, "stem", [])) < len(getattr(gt_q, "stem", [])):
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.CLEANING_DAMAGE,
                    question_number=q_num,
                    stage="S2",
                    description=f"Content missing in Q{q_num} likely dropped by S2 cleaner",
                )
            )
        # Case D: Default to OCR misread
        else:
            errors.append(
                ClassifiedError(
                    error_class=ErrorClass.OCR_MISREAD,
                    question_number=q_num,
                    stage="S3",
                    description=f"Text recognition error in Q{q_num}",
                    evidence={"extracted": final_text, "gt": gt_text},
                )
            )

    return errors
