"""Performance Ratchet Guard for CI/CD & local verification (Phase O8).

Enforces:
1. Stage execution times must not regress by > 10% vs recorded baseline.
2. Peak RSS memory must not regress by > 10% vs recorded baseline.
3. Accuracy metrics must not regress by > 0.5 pp vs baseline.
4. 'make ratchet' / ratchet_tighten() to lock in performance gains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple


class RatchetViolation(NamedTuple):
    metric: str
    baseline_value: float
    current_value: float
    threshold_value: float
    message: str


class RatchetResult(NamedTuple):
    passed: bool
    violations: list[RatchetViolation]
    summary: dict[str, Any]


# Recorded performance baseline after Phase O0–O7 optimizations
DEFAULT_PERF_BASELINE: dict[str, Any] = {
    "version": "2.0.0",
    "timing_targets_sec": {
        "digital_path_per_page": 0.25,      # Baseline was 1.48s (≥5x faster)
        "scanned_path_per_page": 1.15,      # Baseline was 2.66s (≥2x faster)
        "import_time_cli": 0.45,            # Baseline was 1.2s (<0.5s target)
        "s0_intake": 0.20,
        "s1_profile": 0.10,
        "s2_clean": 0.35,                   # 1/8 scale downsampling
        "s3_parse_digital": 0.05,           # Path A model-bypass
        "s4_structure": 0.25,
        "s5_normalize": 0.30,               # Unified S5 pass
        "s6_figures": 0.45,
        "s8_verify": 0.20,                  # Tier-gated rules
        "s7_repair": 0.15,
        "s9_package": 0.25,
    },
    "memory_targets_mb": {
        "peak_rss_lite": 220.0,             # Baseline was 480MB (≥40% lower)
        "peak_rss_standard": 450.0,
    },
    "accuracy_targets": {
        "sequence_accuracy": 0.98,
        "cer_mean": 0.025,
        "wer_mean": 0.05,
        "option_accuracy": 0.95,
        "repair_harm_rate": 0.001,           # ≤0.1%
    },
    "tolerances": {
        "time_regression_pct": 0.10,        # Max 10% slower
        "rss_regression_pct": 0.10,         # Max 10% higher RSS
        "accuracy_regression_pp": 0.005,    # Max 0.5 pp regression
    },
}


def check_perf_ratchet(
    current_metrics: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> RatchetResult:
    """Verify current benchmark metrics against the ratchet baseline.

    Args:
        current_metrics: Observed timings, memory, and accuracy metrics.
        baseline: Baseline dictionary (defaults to DEFAULT_PERF_BASELINE).

    Returns:
        RatchetResult containing pass status and any detected violations.
    """
    base = baseline or DEFAULT_PERF_BASELINE
    violations: list[RatchetViolation] = []

    time_tol = base.get("tolerances", {}).get("time_regression_pct", 0.10)
    rss_tol = base.get("tolerances", {}).get("rss_regression_pct", 0.10)
    acc_tol = base.get("tolerances", {}).get("accuracy_regression_pp", 0.005)

    # 1. Check timings (lower is better, max regression +10%)
    timings = base.get("timing_targets_sec", {})
    cur_timings = current_metrics.get("timing_targets_sec", current_metrics.get("timings", {}))

    for k, b_val in timings.items():
        if k in cur_timings:
            c_val = float(cur_timings[k])
            ceiling = b_val * (1.0 + time_tol)
            if c_val > ceiling:
                violations.append(
                    RatchetViolation(
                        metric=f"timing:{k}",
                        baseline_value=b_val,
                        current_value=c_val,
                        threshold_value=ceiling,
                        message=f"Stage timing '{k}' regressed by >{time_tol*100:.0f}%: {c_val:.3f}s > {ceiling:.3f}s (baseline {b_val:.3f}s)",
                    )
                )

    # 2. Check memory RSS (lower is better, max regression +10%)
    mem_targets = base.get("memory_targets_mb", {})
    cur_mem = current_metrics.get("memory_targets_mb", current_metrics.get("memory", {}))

    for k, b_val in mem_targets.items():
        if k in cur_mem:
            c_val = float(cur_mem[k])
            ceiling = b_val * (1.0 + rss_tol)
            if c_val > ceiling:
                violations.append(
                    RatchetViolation(
                        metric=f"memory:{k}",
                        baseline_value=b_val,
                        current_value=c_val,
                        threshold_value=ceiling,
                        message=f"Memory RSS '{k}' regressed by >{rss_tol*100:.0f}%: {c_val:.1f}MB > {ceiling:.1f}MB (baseline {b_val:.1f}MB)",
                    )
                )

    # 3. Check accuracy metrics
    acc_targets = base.get("accuracy_targets", {})
    cur_acc = current_metrics.get("accuracy_targets", current_metrics.get("accuracy", {}))

    for k, b_val in acc_targets.items():
        if k in cur_acc:
            c_val = float(cur_acc[k])
            if k in ("cer_mean", "wer_mean", "repair_harm_rate"):
                # Lower is better
                ceiling = b_val + acc_tol
                if c_val > ceiling:
                    violations.append(
                        RatchetViolation(
                            metric=f"accuracy:{k}",
                            baseline_value=b_val,
                            current_value=c_val,
                            threshold_value=ceiling,
                            message=f"Error rate '{k}' increased beyond tolerance: {c_val:.4f} > {ceiling:.4f}",
                        )
                    )
            else:
                # Higher is better
                floor = b_val - acc_tol
                if c_val < floor:
                    violations.append(
                        RatchetViolation(
                            metric=f"accuracy:{k}",
                            baseline_value=b_val,
                            current_value=c_val,
                            threshold_value=floor,
                            message=f"Accuracy metric '{k}' regressed beyond tolerance: {c_val:.4f} < {floor:.4f}",
                        )
                    )

    passed = len(violations) == 0
    return RatchetResult(
        passed=passed,
        violations=violations,
        summary={
            "passed": passed,
            "violations_count": len(violations),
            "checked_timings": len(cur_timings),
            "checked_memory": len(cur_mem),
            "checked_accuracy": len(cur_acc),
        },
    )


def tighten_ratchet(
    current_metrics: dict[str, Any],
    baseline_path: Path | str,
) -> dict[str, Any]:
    """Ratchet forward baseline targets when verified improvements occur.

    Only improves targets (monotonically non-decreasing standards).
    """
    p = Path(baseline_path)
    base = json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(DEFAULT_PERF_BASELINE)

    # Tighten timings (take minimum if faster)
    cur_timings = current_metrics.get("timing_targets_sec", current_metrics.get("timings", {}))
    for k, v in cur_timings.items():
        if k in base["timing_targets_sec"]:
            base["timing_targets_sec"][k] = min(base["timing_targets_sec"][k], float(v))

    # Tighten RSS
    cur_mem = current_metrics.get("memory_targets_mb", current_metrics.get("memory", {}))
    for k, v in cur_mem.items():
        if k in base["memory_targets_mb"]:
            base["memory_targets_mb"][k] = min(base["memory_targets_mb"][k], float(v))

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return base
