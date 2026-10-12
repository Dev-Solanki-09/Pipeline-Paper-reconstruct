"""
Sequential pipeline runner with resume support.

Executes stages in order, saving a checkpoint (document JSON + manifest)
after each successful stage. On --resume, detects the last completed stage
and restarts from the next one.

Design decisions:
- Sequential, not parallel: simpler, debuggable, sufficient for M1.
- Each stage gets its own subdirectory under the run dir.
- Document state is saved as JSON after every stage for crash recovery.
- Manifest is updated atomically after each stage.
- Page-level failure policy is configurable (fail_fast / fail_page / fail_warn).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from examforge.config import ExamForgeConfig
from examforge.ir.schema import ExamDocument, IssueSeverity, PageStatus
from examforge.orchestrator.manifest import Manifest
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


# Exit codes (section 12 of architecture doc)
EXIT_OK = 0  # All gates pass
EXIT_WARNINGS = 10  # Pass with warnings
EXIT_NEEDS_REVIEW = 20  # Needs human review
EXIT_FAILED = 30  # Failed


class RunDirectory:
    """
    Manages the filesystem layout for a single pipeline run.

    Layout:
        runs/<run_id>/
            manifest.json
            document.json          # Latest IR state
            stages/
                s0_intake/
                    document.json  # IR snapshot after this stage
                    pages/         # Stage-specific outputs
                s9_package/
                    document.json
                    output.html
    """

    def __init__(self, base_dir: Path, run_id: str):
        self.root = base_dir / run_id
        self.run_id = run_id

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def document_path(self) -> Path:
        return self.root / "document.json"

    def stage_dir(self, stage_name: str) -> Path:
        return self.root / "stages" / stage_name

    def stage_checkpoint(self, stage_name: str) -> Path:
        return self.stage_dir(stage_name) / "document.json"

    def create(self) -> None:
        """Create the run directory structure."""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "stages").mkdir(exist_ok=True)

    def exists(self) -> bool:
        return self.root.exists()

    def save_document(self, doc: ExamDocument, stage_name: str | None = None) -> None:
        """
        Save document state. Writes to both the root document.json
        and the stage-specific checkpoint.
        """
        doc_json = doc.model_dump_json(indent=2)

        # Always update the root document
        _atomic_write(self.document_path, doc_json)

        # Also save stage-specific checkpoint
        if stage_name:
            stage_cp = self.stage_checkpoint(stage_name)
            stage_cp.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(stage_cp, doc_json)

    def load_document(self, stage_name: str | None = None) -> ExamDocument:
        """Load document from a stage checkpoint or the root."""
        if stage_name:
            path = self.stage_checkpoint(stage_name)
        else:
            path = self.document_path

        if not path.exists():
            raise FileNotFoundError(f"No document checkpoint at {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        return ExamDocument(**data)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically via rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _generate_run_id() -> str:
    """Generate a timestamped run ID."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Add a short random suffix to avoid collisions
    import secrets
    suffix = secrets.token_hex(3)
    return f"{ts}_{suffix}"


def _file_hash(path: Path) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _config_hash(config: ExamForgeConfig) -> str:
    """Deterministic hash of the config for traceability."""
    raw = config.model_dump_json()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class PipelineRunner:
    """
    Runs a sequence of stages against an exam document.

    Usage:
        runner = PipelineRunner(stages=[S0Intake(), S9Package()], config=cfg, spec=spec)
        result = runner.execute(source_path=Path("exam.pdf"))

        # Or resume a failed/interrupted run:
        result = runner.resume(run_id="20261011_134500_abc123")
    """

    def __init__(
        self,
        stages: list[Stage],
        config: ExamForgeConfig,
        spec: Spec,
    ):
        self.stages = stages
        self.config = config
        self.spec = spec
        self.runs_dir = config.paths.runs

    def execute(self, source_path: Path) -> RunResult:
        """
        Execute the full pipeline on a source file.

        Creates a new run directory, initializes the document, and
        runs each stage sequentially with checkpoints.
        """
        source_path = source_path.resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Create run directory
        run_id = _generate_run_id()
        run_dir = RunDirectory(self.runs_dir, run_id)
        run_dir.create()

        logger.info("Starting run %s for %s", run_id, source_path.name)

        # Initialize document
        document = ExamDocument(
            source_path=str(source_path),
            source_hash=_file_hash(source_path),
        )

        # Initialize manifest
        manifest = Manifest(
            run_id=run_id,
            source_path=str(source_path),
            source_hash=document.source_hash,
            config_hash=_config_hash(self.config),
            spec_hash=self.spec.hash(),
            mode=self.config.mode,
        )
        manifest.save(run_dir.manifest_path)

        # Run stages
        return self._run_stages(
            document=document,
            run_dir=run_dir,
            manifest=manifest,
            start_index=0,
        )

    def resume(self, run_id: str) -> RunResult:
        """
        Resume a previously interrupted run from the last completed stage.
        """
        run_dir = RunDirectory(self.runs_dir, run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir.root}")

        manifest = Manifest.load(run_dir.manifest_path)
        completed = manifest.get_completed_stage_names()

        if not completed:
            # Nothing completed — restart from the beginning
            document = run_dir.load_document()
            start_index = 0
        else:
            # Find the index of the next stage after the last completed one
            last = completed[-1]
            document = run_dir.load_document(stage_name=last)
            start_index = self._find_stage_index(last) + 1

        if start_index >= len(self.stages):
            logger.info("All stages already completed for run %s", run_id)
            return RunResult(
                run_id=run_id,
                run_dir=run_dir.root,
                document=document,
                manifest=manifest,
                exit_code=self._compute_exit_code(document),
            )

        logger.info(
            "Resuming run %s from stage %s",
            run_id,
            self.stages[start_index].name,
        )

        return self._run_stages(
            document=document,
            run_dir=run_dir,
            manifest=manifest,
            start_index=start_index,
        )

    def _run_stages(
        self,
        document: ExamDocument,
        run_dir: RunDirectory,
        manifest: Manifest,
        start_index: int,
    ) -> RunResult:
        """Core loop: run stages from start_index, save checkpoints."""
        for i in range(start_index, len(self.stages)):
            stage = self.stages[i]
            stage_name = stage.name
            s_dir = run_dir.stage_dir(stage_name)
            s_dir.mkdir(parents=True, exist_ok=True)

            logger.info("-- Stage %s --", stage_name)
            manifest.record_stage_start(stage_name)
            manifest.save(run_dir.manifest_path)

            ctx = StageContext(
                document=document,
                run_dir=run_dir.root,
                config=self.config,
                spec=self.spec,
                stage_dir=s_dir,
            )

            # Pre-conditions
            violations = stage.validate_preconditions(ctx)
            if violations:
                error_msg = f"Precondition failures: {'; '.join(violations)}"
                logger.error("  [FAIL] %s", error_msg)
                manifest.record_stage_failure(stage_name, error_msg)
                manifest.status = "failed"
                manifest.exit_code = EXIT_FAILED
                manifest.completed_at = datetime.now()
                manifest.save(run_dir.manifest_path)
                return RunResult(
                    run_id=manifest.run_id,
                    run_dir=run_dir.root,
                    document=document,
                    manifest=manifest,
                    exit_code=EXIT_FAILED,
                    error=error_msg,
                )

            # Execute
            t0 = time.monotonic()
            try:
                result = stage.run(ctx)
            except Exception as exc:
                error_msg = f"Stage {stage_name} raised: {exc}"
                logger.exception("  [FAIL] %s", error_msg)
                manifest.record_stage_failure(stage_name, error_msg)
                manifest.status = "failed"
                manifest.exit_code = EXIT_FAILED
                manifest.completed_at = datetime.now()
                manifest.save(run_dir.manifest_path)
                run_dir.save_document(document, stage_name)
                return RunResult(
                    run_id=manifest.run_id,
                    run_dir=run_dir.root,
                    document=document,
                    manifest=manifest,
                    exit_code=EXIT_FAILED,
                    error=error_msg,
                )
            elapsed = time.monotonic() - t0

            # Merge issues into document
            document = result.document
            for issue in result.issues:
                document.add_issue(issue)
            document.last_stage = stage_name

            # Post-conditions
            violations = stage.validate_postconditions(result)
            if violations:
                error_msg = f"Postcondition failures: {'; '.join(violations)}"
                logger.error("  [FAIL] %s", error_msg)
                manifest.record_stage_failure(stage_name, error_msg)

                # Check fail policy
                if self.config.fail_policy == "fail_fast":
                    manifest.status = "failed"
                    manifest.exit_code = EXIT_FAILED
                    manifest.completed_at = datetime.now()
                    manifest.save(run_dir.manifest_path)
                    run_dir.save_document(document, stage_name)
                    return RunResult(
                        run_id=manifest.run_id,
                        run_dir=run_dir.root,
                        document=document,
                        manifest=manifest,
                        exit_code=EXIT_FAILED,
                        error=error_msg,
                    )
                # fail_page / fail_warn: log and continue
                logger.warning("  [WARN] Continuing despite postcondition failure (policy=%s)", self.config.fail_policy)

            # Record success
            metrics = {**result.metrics, "elapsed_s": round(elapsed, 3)}
            manifest.record_stage_complete(
                stage_name,
                metrics=metrics,
                issue_count=len(result.issues),
            )

            # Checkpoint
            run_dir.save_document(document, stage_name)
            manifest.save(run_dir.manifest_path)

            logger.info(
                "  [OK] %s completed in %.1fs (%d issues)",
                stage_name,
                elapsed,
                len(result.issues),
            )

        # All stages complete
        exit_code = self._compute_exit_code(document)
        manifest.status = "completed" if exit_code == EXIT_OK else (
            "needs_review" if exit_code == EXIT_NEEDS_REVIEW else "completed"
        )
        manifest.exit_code = exit_code
        manifest.completed_at = datetime.now()
        manifest.total_pages = len(document.pages)
        manifest.total_questions = len(document.questions)
        manifest.total_issues = len(document.issues)
        manifest.blocker_count = len(document.blocker_issues())
        manifest.save(run_dir.manifest_path)

        logger.info(
            "Run %s finished -- exit %d, %d pages, %d questions, %d issues (%d blockers)",
            manifest.run_id,
            exit_code,
            manifest.total_pages,
            manifest.total_questions,
            manifest.total_issues,
            manifest.blocker_count,
        )

        return RunResult(
            run_id=manifest.run_id,
            run_dir=run_dir.root,
            document=document,
            manifest=manifest,
            exit_code=exit_code,
        )

    def _compute_exit_code(self, document: ExamDocument) -> int:
        """Determine exit code from document state."""
        blockers = document.blocker_issues()
        if blockers:
            return EXIT_FAILED

        warnings = [
            i for i in document.issues
            if i.severity == IssueSeverity.WARNING and not i.resolved
        ]
        disputed = [
            b for b in document.blocks
            if b.status.value == "disputed"
        ]

        if disputed:
            return EXIT_NEEDS_REVIEW
        if warnings:
            return EXIT_WARNINGS
        return EXIT_OK

    def _find_stage_index(self, stage_name: str) -> int:
        """Find the index of a stage by name."""
        for i, stage in enumerate(self.stages):
            if stage.name == stage_name:
                return i
        raise ValueError(f"Unknown stage: {stage_name}")


class RunResult:
    """Result of a pipeline execution."""

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        document: ExamDocument,
        manifest: Manifest,
        exit_code: int,
        error: str | None = None,
    ):
        self.run_id = run_id
        self.run_dir = run_dir
        self.document = document
        self.manifest = manifest
        self.exit_code = exit_code
        self.error = error

    @property
    def success(self) -> bool:
        return self.exit_code in (EXIT_OK, EXIT_WARNINGS)

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "exit_code": self.exit_code,
            "status": self.manifest.status,
            "pages": self.manifest.total_pages,
            "questions": self.manifest.total_questions,
            "issues": self.manifest.total_issues,
            "blockers": self.manifest.blocker_count,
            "error": self.error,
        }
