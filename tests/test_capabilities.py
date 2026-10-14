"""Tests for capability negotiation in PipelineRunner."""

from __future__ import annotations

import pytest

from examforge.config import ExamForgeConfig
from examforge.orchestrator.runner import CapabilityError, PipelineRunner
from examforge.profiles.schema import ExamProfile
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult


class MockProviderStage(Stage):
    name = "mock_provider"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["cap_a", "cap_b"]

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(document=ctx.document)


def test_capability_negotiation_pass():
    profile = ExamProfile(
        id="test_pass",
        name="Test Pass",
        requires=["cap_a"],
        capability_policy="fail",
    )
    runner = PipelineRunner(
        stages=[MockProviderStage()],
        config=ExamForgeConfig(),
        spec=Spec.default(),
        profile=profile,
    )
    # Negotiating should succeed without error
    runner.negotiate_capabilities()


def test_capability_negotiation_fail_policy():
    profile = ExamProfile(
        id="test_fail",
        name="Test Fail",
        requires=["cap_missing"],
        capability_policy="fail",
    )
    runner = PipelineRunner(
        stages=[MockProviderStage()],
        config=ExamForgeConfig(),
        spec=Spec.default(),
        profile=profile,
    )
    with pytest.raises(CapabilityError) as exc_info:
        runner.negotiate_capabilities()

    assert "cap_missing" in str(exc_info.value)
    assert "test_fail" in str(exc_info.value)


def test_capability_negotiation_warn_policy(caplog):
    profile = ExamProfile(
        id="test_warn",
        name="Test Warn",
        requires=["cap_missing"],
        capability_policy="warn",
    )
    runner = PipelineRunner(
        stages=[MockProviderStage()],
        config=ExamForgeConfig(),
        spec=Spec.default(),
        profile=profile,
    )
    runner.negotiate_capabilities()
    assert any("cap_missing" in record.message for record in caplog.records)
