"""Run comparison and regression detection tools for ExamForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examforge.eval.scorer import EvaluationResult


def compare_metrics(
    current: EvaluationResult | dict[str, Any],
    baseline: dict[str, Any],
    tolerance: float = 0.005,
) -> tuple[bool, list[str]]:
    """
    Check if any metric in current has regressed by more than tolerance (>0.5 pp)
    compared to the baseline.
    Returns (passed, list_of_regression_reasons).
    """
    cur_dict = current.to_dict() if isinstance(current, EvaluationResult) else current
    regressions: list[str] = []

    # Higher is better metrics
    higher_better = [
        "sequence_accuracy",
        "count_match",
        "option_accuracy",
        "kind_accuracy",
        "language_completeness",
        "figure_iou_mean",
        "table_similarity",
        "aggregate_score",
    ]
    # Lower is better metrics
    lower_better = [
        "cer_mean",
        "cer_p95",
        "wer_mean",
        "wer_p95",
    ]

    for m in higher_better:
        if m in baseline and m in cur_dict:
            b_val = float(baseline[m])
            c_val = float(cur_dict[m])
            if c_val < (b_val - tolerance):
                regressions.append(
                    f"Regression in '{m}': dropped from {b_val:.4f} to {c_val:.4f} (allowed drop: {tolerance:.4f})"
                )

    for m in lower_better:
        if m in baseline and m in cur_dict:
            b_val = float(baseline[m])
            c_val = float(cur_dict[m])
            if c_val > (b_val + tolerance):
                regressions.append(
                    f"Regression in '{m}': increased error from {b_val:.4f} to {c_val:.4f} (allowed increase: {tolerance:.4f})"
                )

    passed = len(regressions) == 0
    return passed, regressions


def compare_runs_per_question(run_a_dir: Path | str, run_b_dir: Path | str) -> dict[str, Any]:
    """Generate question-by-question diff between two pipeline run outputs."""
    p_a = Path(run_a_dir) / "document.json"
    p_b = Path(run_b_dir) / "document.json"

    if not p_a.exists():
        raise FileNotFoundError(f"Run A document missing: {p_a}")
    if not p_b.exists():
        raise FileNotFoundError(f"Run B document missing: {p_b}")

    with open(p_a, encoding="utf-8") as f:
        doc_a = json.load(f)
    with open(p_b, encoding="utf-8") as f:
        doc_b = json.load(f)

    qs_a = {q.get("number"): q for q in doc_a.get("questions", [])}
    qs_b = {q.get("number"): q for q in doc_b.get("questions", [])}

    all_nums = sorted(list(set(qs_a.keys()) | set(qs_b.keys())))
    diffs = []

    for num in all_nums:
        qa = qs_a.get(num)
        qb = qs_b.get(num)
        if qa is None:
            diffs.append({"number": num, "status": "added_in_b", "stem": qb.get("stem_text_en", "")[:60]})
        elif qb is None:
            diffs.append({"number": num, "status": "missing_in_b", "stem": qa.get("stem_text_en", "")[:60]})
        else:
            stem_a = qa.get("stem_text_en", "")
            stem_b = qb.get("stem_text_en", "")
            opt_cnt_a = len(qa.get("options", []))
            opt_cnt_b = len(qb.get("options", []))
            diffs.append({
                "number": num,
                "status": "matched" if stem_a == stem_b and opt_cnt_a == opt_cnt_b else "different",
                "stem_equal": stem_a == stem_b,
                "options_equal": opt_cnt_a == opt_cnt_b,
            })

    return {
        "run_a": str(run_a_dir),
        "run_b": str(run_b_dir),
        "total_questions_a": len(qs_a),
        "total_questions_b": len(qs_b),
        "differences": diffs,
    }
