"""Fault injection tests: verify G1 Fail Closed and error resilience."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.orchestrator.runner import EXIT_FAILED, PipelineRunner
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult


class ExplodingStage(Stage):
    """Test stage that raises an unexpected exception."""

    name = "exploding_stage"

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        return []

    def run(self, ctx: StageContext) -> StageResult:
        raise RuntimeError("Injected unexpected fault!")

    def validate_postconditions(self, result: StageResult) -> list[str]:
        return []


class TestFaultInjection:
    def test_missing_input_file(self, tmp_path):
        """Non-existent input file must raise FileNotFoundError immediately."""
        non_existent = tmp_path / "does_not_exist.pdf"
        runner = PipelineRunner(stages=[], config=ExamForgeConfig(), spec=Spec.default())
        with pytest.raises(FileNotFoundError, match="not found"):
            runner.execute(non_existent)

    def test_empty_input_file(self, tmp_path):
        """0-byte file must fail closed cleanly."""
        empty_file = tmp_path / "empty.pdf"
        empty_file.write_bytes(b"")

        from examforge.cli import _build_stages

        config = ExamForgeConfig(paths={"runs": tmp_path / "runs"})
        stages = _build_stages(config)
        runner = PipelineRunner(stages=stages, config=config, spec=Spec.default())
        result = runner.execute(empty_file)

        assert result.exit_code == EXIT_FAILED
        assert result.error is not None

    def test_unhandled_stage_exception(self, sample_pdf_path, tmp_path):
        """Unhandled stage exception halts pipeline, records error, and exits with 30."""
        if sample_pdf_path is None or not sample_pdf_path.exists():
            pytest.skip("Sample PDF not available")

        from examforge.stages.s0_intake import S0Intake

        config = ExamForgeConfig(paths={"runs": tmp_path / "runs"}, max_pages=1)
        stages = [S0Intake(), ExplodingStage()]
        runner = PipelineRunner(stages=stages, config=config, spec=Spec.default())

        result = runner.execute(sample_pdf_path)
        assert result.exit_code == EXIT_FAILED
        assert result.error is not None
        assert "Injected unexpected fault!" in result.error
