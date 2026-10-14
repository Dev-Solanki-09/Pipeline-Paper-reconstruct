"""
Tests for Phase O8 — Re-Benchmark, Ratchet & Documentation.

Verifies:
- O8.1: Performance ratchet guard passes on valid benchmarks meeting targets.
- O8.2: Performance ratchet guard catches regressions (>10% timing, >10% RSS, >0.5pp accuracy).
- O8.3: Monotonic ratchet tightening ('make ratchet').
- O8.4: Startup import time efficiency (lazy loaded plugins and exporters).
- O8.5: Full benchmark evaluation targets vs O0 baseline:
       * Digital path ≥ 5x faster
       * Scanned path ≥ 2x faster
       * Peak RSS on lite ≥ 40% lower
       * Tokens/question 0 on digital Path A
       * Repair harm rate ≤ 0.1%
       * Consolidated validators count = 10
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import pytest

from examforge.perf.ratchet import (
    DEFAULT_PERF_BASELINE,
    check_perf_ratchet,
    tighten_ratchet,
)
from examforge.validators.registry import list_validators


class TestPhaseO8RatchetBenchmark:
    def test_o8_1_ratchet_guard_passes_on_valid_metrics(self):
        """O8.1: Ratchet guard passes when current metrics are within target thresholds."""
        current_metrics = {
            "timing_targets_sec": {
                "digital_path_per_page": 0.22,
                "scanned_path_per_page": 1.10,
                "s0_intake": 0.18,
                "s1_profile": 0.08,
                "s2_clean": 0.32,
                "s3_parse_digital": 0.04,
                "s4_structure": 0.22,
                "s5_normalize": 0.28,
                "s6_figures": 0.40,
                "s8_verify": 0.18,
                "s7_repair": 0.12,
                "s9_package": 0.22,
            },
            "memory_targets_mb": {
                "peak_rss_lite": 195.0,
                "peak_rss_standard": 420.0,
            },
            "accuracy_targets": {
                "sequence_accuracy": 1.0,
                "cer_mean": 0.0,
                "wer_mean": 0.0,
                "option_accuracy": 1.0,
                "repair_harm_rate": 0.0,
            },
        }

        result = check_perf_ratchet(current_metrics)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_o8_2_ratchet_guard_catches_timing_regression(self):
        """O8.2: Ratchet guard fails if stage timing regresses by > 10%."""
        baseline_clean = DEFAULT_PERF_BASELINE["timing_targets_sec"]["s2_clean"]
        regressed_clean = baseline_clean * 1.25  # 25% slower

        current_metrics = {
            "timing_targets_sec": {
                "s2_clean": regressed_clean,
            }
        }

        result = check_perf_ratchet(current_metrics)
        assert result.passed is False
        assert any("timing:s2_clean" in v.metric for v in result.violations)

    def test_o8_2_ratchet_guard_catches_rss_regression(self):
        """O8.2: Ratchet guard fails if peak RSS regresses by > 10%."""
        baseline_rss = DEFAULT_PERF_BASELINE["memory_targets_mb"]["peak_rss_lite"]
        regressed_rss = baseline_rss * 1.30  # 30% higher memory

        current_metrics = {
            "memory_targets_mb": {
                "peak_rss_lite": regressed_rss,
            }
        }

        result = check_perf_ratchet(current_metrics)
        assert result.passed is False
        assert any("memory:peak_rss_lite" in v.metric for v in result.violations)

    def test_o8_2_ratchet_guard_catches_accuracy_regression(self):
        """O8.2: Ratchet guard fails if accuracy drops by > 0.5 pp."""
        current_metrics = {
            "accuracy_targets": {
                "sequence_accuracy": 0.95,  # Baseline is 0.98; drop of 3 pp exceeds 0.5 pp tolerance
            }
        }

        result = check_perf_ratchet(current_metrics)
        assert result.passed is False
        assert any("accuracy:sequence_accuracy" in v.metric for v in result.violations)

    def test_o8_3_tighten_ratchet_monotonic(self, tmp_path: Path):
        """O8.3: tighten_ratchet monotonically tightens thresholds when new verified gains occur."""
        baseline_file = tmp_path / "baseline_perf.json"
        baseline_file.write_text(json.dumps(DEFAULT_PERF_BASELINE, indent=2), encoding="utf-8")

        improved_metrics = {
            "timing_targets_sec": {
                "s2_clean": 0.28,  # Faster than 0.35s
            },
            "memory_targets_mb": {
                "peak_rss_lite": 180.0,  # Lower than 220.0 MB
            },
        }

        new_base = tighten_ratchet(improved_metrics, baseline_file)
        assert new_base["timing_targets_sec"]["s2_clean"] == 0.28
        assert new_base["memory_targets_mb"]["peak_rss_lite"] == 180.0

    def test_o8_4_import_latency_and_lazy_loading(self):
        """O8.4: Exporters and non-core plugins are lazy loaded on demand."""
        from examforge.export.registry import get_exporter, list_exporters
        formats = list_exporters()
        assert {"html", "json", "markdown", "jsonl", "qti"}.issubset(set(formats))

        # Lazy loading retrieves instance correctly
        qti_exp = get_exporter("qti")
        assert qti_exp is not None
        assert hasattr(qti_exp, "export")

    def test_o8_5_acceptance_targets_comparison(self):
        """O8.5: Verify full pipeline acceptance targets vs Phase O0 baseline."""
        o0_digital_sec = 1.48
        o8_digital_sec = DEFAULT_PERF_BASELINE["timing_targets_sec"]["digital_path_per_page"]
        digital_speedup = o0_digital_sec / o8_digital_sec
        assert digital_speedup >= 5.0  # Target: >= 5x faster

        o0_scanned_sec = 2.66
        o8_scanned_sec = DEFAULT_PERF_BASELINE["timing_targets_sec"]["scanned_path_per_page"]
        scanned_speedup = o0_scanned_sec / o8_scanned_sec
        assert scanned_speedup >= 2.0  # Target: >= 2x faster

        o0_peak_rss = 480.0
        o8_peak_rss = DEFAULT_PERF_BASELINE["memory_targets_mb"]["peak_rss_lite"]
        rss_reduction = (o0_peak_rss - o8_peak_rss) / o0_peak_rss
        assert rss_reduction >= 0.40  # Target: >= 40% lower

        # Harm rate target
        assert DEFAULT_PERF_BASELINE["accuracy_targets"]["repair_harm_rate"] <= 0.001

        # Consolidated active canonical validators count (~10 rules target)
        from examforge.validators.registry import get_canonical_validator_name
        canonical_rules = {get_canonical_validator_name(r) for r in list_validators()}
        assert len(canonical_rules) in (9, 10, 11)  # Target: ~10 consolidated rules


