"""Tests for the pipeline runner and manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    Issue,
    IssueSeverity,
)
from examforge.orchestrator.manifest import Manifest
from examforge.orchestrator.runner import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_WARNINGS,
    PipelineRunner,
    RunDirectory,
    _generate_run_id,
)
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult

# ---------------------------------------------------------------------------
# Stub stages for testing
# ---------------------------------------------------------------------------


class PassStage(Stage):
    """A stage that always succeeds."""

    name = "pass_stage"

    def run(self, ctx: StageContext) -> StageResult:
        ctx.document.metadata.exam_name = "Modified by PassStage"
        return StageResult(
            document=ctx.document,
            metrics={"processed": True},
            issues=[],
        )


class FailStage(Stage):
    """A stage that always raises an exception."""

    name = "fail_stage"

    def run(self, ctx: StageContext) -> StageResult:
        raise RuntimeError("Intentional failure for testing")


class IssueStage(Stage):
    """A stage that produces issues but succeeds."""

    name = "issue_stage"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(
            document=ctx.document,
            metrics={"checked": True},
            issues=[
                Issue(
                    id="test_warning",
                    stage=self.name,
                    severity=IssueSeverity.WARNING,
                    message="Test warning",
                ),
            ],
        )


class PostconditionFailStage(Stage):
    """A stage whose postconditions fail."""

    name = "postfail_stage"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(document=ctx.document)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        return ["Postcondition violated: test"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunDirectory:
    def test_create_and_structure(self, tmp_path: Path):
        rd = RunDirectory(tmp_path, "test_run_001")
        rd.create()

        assert rd.root.exists()
        assert (rd.root / "stages").exists()
        assert rd.manifest_path == rd.root / "manifest.json"

    def test_save_and_load_document(self, tmp_path: Path, empty_document):
        rd = RunDirectory(tmp_path, "test_run_002")
        rd.create()

        rd.save_document(empty_document, "s0_intake")

        # Root document exists
        assert rd.document_path.exists()

        # Stage checkpoint exists
        assert rd.stage_checkpoint("s0_intake").exists()

        # Load and verify
        loaded = rd.load_document("s0_intake")
        assert loaded.source_path == empty_document.source_path
        assert loaded.metadata.exam_name == empty_document.metadata.exam_name


class TestManifest:
    def test_stage_lifecycle(self):
        m = Manifest(run_id="test", source_path="/test.pdf")

        m.record_stage_start("s0_intake")
        assert m.current_stage == "s0_intake"
        assert len(m.stages) == 1
        assert m.stages[0].status == "running"

        m.record_stage_complete("s0_intake", metrics={"pages": 5})
        assert m.current_stage is None
        assert m.last_completed_stage == "s0_intake"
        assert m.stages[0].status == "completed"
        assert m.stages[0].metrics == {"pages": 5}

    def test_stage_failure(self):
        m = Manifest(run_id="test", source_path="/test.pdf")
        m.record_stage_start("s3_parse")
        m.record_stage_failure("s3_parse", "OCR engine timeout")

        assert m.stages[0].status == "failed"
        assert m.stages[0].error == "OCR engine timeout"

    def test_save_and_load(self, tmp_path: Path):
        m = Manifest(run_id="test_save", source_path="/test.pdf", mode="fast")
        m.record_stage_start("s0")
        m.record_stage_complete("s0")

        path = tmp_path / "manifest.json"
        m.save(path)
        assert path.exists()

        loaded = Manifest.load(path)
        assert loaded.run_id == "test_save"
        assert loaded.mode == "fast"
        assert loaded.get_completed_stage_names() == ["s0"]

    def test_completed_stage_names(self):
        m = Manifest(run_id="test", source_path="/test.pdf")
        m.record_stage_start("s0")
        m.record_stage_complete("s0")
        m.record_stage_start("s1")
        m.record_stage_complete("s1")
        m.record_stage_start("s2")
        m.record_stage_failure("s2", "error")

        assert m.get_completed_stage_names() == ["s0", "s1"]


class TestPipelineRunner:
    def _make_source_pdf(self, tmp_path: Path) -> Path:
        """Create a minimal dummy file to act as source."""
        pdf = tmp_path / "test_exam.pdf"
        pdf.write_bytes(b"%PDF-1.4 dummy content for hash testing")
        return pdf

    def test_successful_run(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(
            stages=[PassStage()],
            config=config,
            spec=spec,
        )
        result = runner.execute(pdf)

        assert result.exit_code == EXIT_OK
        assert result.success
        assert result.manifest.status == "completed"
        assert result.document.metadata.exam_name == "Modified by PassStage"

        # Manifest on disk
        manifest_path = result.run_dir / "manifest.json"
        assert manifest_path.exists()

    def test_failing_stage(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(
            stages=[PassStage(), FailStage()],
            config=config,
            spec=spec,
        )
        result = runner.execute(pdf)

        assert result.exit_code == EXIT_FAILED
        assert not result.success
        assert result.error is not None
        assert "Intentional failure" in result.error

    def test_issues_produce_warnings_exit(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(
            stages=[IssueStage()],
            config=config,
            spec=spec,
        )
        result = runner.execute(pdf)

        assert result.exit_code == EXIT_WARNINGS
        assert result.success  # Warnings don't fail
        assert len(result.document.issues) == 1

    def test_postcondition_fail_fast(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            fail_policy="fail_fast",
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(
            stages=[PostconditionFailStage(), PassStage()],
            config=config,
            spec=spec,
        )
        result = runner.execute(pdf)

        assert result.exit_code == EXIT_FAILED
        # PassStage should NOT have run
        assert result.document.metadata.exam_name != "Modified by PassStage"

    def test_postcondition_fail_page_continues(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            fail_policy="fail_page",
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(
            stages=[PostconditionFailStage(), PassStage()],
            config=config,
            spec=spec,
        )
        result = runner.execute(pdf)

        # Should continue despite postcondition failure
        assert result.document.metadata.exam_name == "Modified by PassStage"

    def test_resume(self, tmp_path: Path):
        pdf = self._make_source_pdf(tmp_path)
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        # First run: two stages, second fails
        runner = PipelineRunner(
            stages=[PassStage(), FailStage()],
            config=config,
            spec=spec,
        )
        result1 = runner.execute(pdf)
        assert result1.exit_code == EXIT_FAILED
        run_id = result1.run_id

        # Resume with a fixed second stage
        runner2 = PipelineRunner(
            stages=[PassStage(), IssueStage()],
            config=config,
            spec=spec,
        )
        result2 = runner2.resume(run_id)

        # Should have resumed from after PassStage
        assert result2.exit_code == EXIT_WARNINGS
        assert result2.success
        assert len(result2.document.issues) == 1

    def test_source_not_found(self, tmp_path: Path):
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        config = ExamForgeConfig(
            paths={"runs": runs_dir, "ledger": tmp_path / "ledger", "cache": tmp_path / ".cache"},
        )
        spec = Spec.default()

        runner = PipelineRunner(stages=[], config=config, spec=spec)

        with pytest.raises(FileNotFoundError):
            runner.execute(tmp_path / "nonexistent.pdf")


class TestGenerateRunId:
    def test_format(self):
        rid = _generate_run_id()
        # Should be timestamp_hex format
        parts = rid.split("_")
        assert len(parts) == 3  # date, time, hex
        assert len(parts[2]) == 6  # 3 bytes = 6 hex chars

    def test_unique(self):
        ids = {_generate_run_id() for _ in range(10)}
        assert len(ids) == 10  # All unique
