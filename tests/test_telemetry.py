"""Tests for ExamForge v2 Telemetry Ledger (Phase 1)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from examforge.telemetry import (
    TelemetryLedger,
    get_peak_rss_bytes,
)


def test_get_peak_rss_bytes_returns_positive_int():
    rss = get_peak_rss_bytes()
    assert isinstance(rss, int)
    assert rss > 0


def test_stage_telemetry_recording():
    ledger = TelemetryLedger(run_id="test_run_001")
    with ledger.track_stage("s0_intake"):
        time.sleep(0.01)
        ledger.record_llm_usage(
            prompt_tokens=100, completion_tokens=50, cost_usd=0.001, question_no=1
        )

    assert len(ledger.stages) == 1
    s0 = ledger.stages[0]
    assert s0.stage_name == "s0_intake"
    assert s0.duration_seconds >= 0.01
    assert s0.prompt_tokens == 100
    assert s0.completion_tokens == 50
    assert s0.total_tokens == 150
    assert s0.cost_usd == pytest.approx(0.001)
    assert 1 in ledger.questions_touched_by_llm


def test_escalation_tier_tracking():
    ledger = TelemetryLedger(run_id="test_run_002")
    ledger.record_escalation("T0_RULE", question_no=1)
    ledger.record_escalation("T2_MCQ_VLM", question_no=2)
    ledger.record_escalation("T2_MCQ_VLM", question_no=3)

    assert ledger.escalation_counts["T0_RULE"] == 1
    assert ledger.escalation_counts["T2_MCQ_VLM"] == 2
    assert ledger.get_escalation_rate() == pytest.approx(3)


def test_telemetry_export_and_load(tmp_path: Path):
    ledger = TelemetryLedger(run_id="test_run_003")
    with ledger.track_stage("s1_profile"):
        pass
    ledger.record_llm_usage(
        prompt_tokens=200, completion_tokens=100, cost_usd=0.002, question_no=42
    )

    export_path = tmp_path / "telemetry.json"
    ledger.save_json(export_path)

    assert export_path.exists()
    loaded = TelemetryLedger.load_json(export_path)
    assert loaded.run_id == "test_run_003"
    assert loaded.total_prompt_tokens == 200
    assert loaded.total_completion_tokens == 100
    assert loaded.total_tokens == 300
    assert 42 in loaded.questions_touched_by_llm
