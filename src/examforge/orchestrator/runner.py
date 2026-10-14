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
from examforge.ir.schema import ExamDocument, IssueSeverity
from examforge.orchestrator.manifest import Manifest
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext

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
        from examforge.orchestrator.io import sanitize_run_id

        safe_id = sanitize_run_id(run_id)
        self.root = base_dir / safe_id
        self.run_id = safe_id

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

    def save_document(
        self,
        doc: ExamDocument,
        stage_name: str | None = None,
        tier: str = "all",
    ) -> None:
        """
        Save document state. Writes to root document.json and optionally
        the stage-specific checkpoint depending on checkpoint tier.
        """
        doc_json = doc.model_dump_json(indent=2)

        # Always update the root document if tier != "none" or if stage_name is None
        if tier != "none" or stage_name is None:
            _atomic_write(self.document_path, doc_json)

        # Also save stage-specific checkpoint based on tier
        if stage_name:
            MAJOR_CHECKPOINTS = {
                "s0_intake",
                "s1_profile",
                "s2_clean",
                "s3_parse",
                "s3_ocr",
                "s6_figures",
                "s9_package",
            }
            should_save_stage = (
                tier == "all"
                or (tier == "major" and stage_name in MAJOR_CHECKPOINTS)
            )
            if should_save_stage:
                stage_cp = self.stage_checkpoint(stage_name)
                stage_cp.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(stage_cp, doc_json)

    def load_document(self, stage_name: str | None = None) -> ExamDocument:
        """Load document from a stage checkpoint or the root."""
        path = self.stage_checkpoint(stage_name) if stage_name else self.document_path

        if not path.exists():
            raise FileNotFoundError(f"No document checkpoint at {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        return ExamDocument(**data)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically via rename and fsync."""
    from examforge.orchestrator.io import atomic_write

    atomic_write(path, content)


def _generate_run_id(paper_hash: str = "") -> str:
    """Generate a versioned run ID: <UTC-ts>_<paper-hash8>_<n>."""
    from examforge.orchestrator.io import generate_run_id

    return generate_run_id(paper_hash=paper_hash)


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


class CapabilityError(ValueError):
    """Raised when the pipeline lacks required capabilities for a profile."""


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
        profile: Any = None,
        compute: str | None = None,
    ):
        self.stages = stages
        self.config = config
        self.spec = spec
        if profile is not None:
            self.profile = profile
        else:
            from examforge.profiles.loader import loader

            try:
                self.profile = loader.load("neet_ug")
            except Exception:
                from examforge.profiles.schema import ExamProfile

                self.profile = ExamProfile(id="default", name="Default Profile")

        from examforge.profiles.compute import resolve_compute_tier

        self.compute_tier = resolve_compute_tier(
            compute or getattr(self.profile, "compute", "standard")
        )
        self.runs_dir = config.paths.runs

    def negotiate_capabilities(self) -> None:
        """
        Check that all capabilities required by profile are satisfied.
        Applies profile's capability_policy ('fail' | 'downgrade' | 'warn').
        """
        available: set[str] = set()
        for s in self.stages:
            if hasattr(s, "capabilities") and callable(s.capabilities):
                available.update(s.capabilities())

        required = set(getattr(self.profile, "requires", []))
        missing = required - available
        if not missing:
            return

        policy = getattr(self.profile, "capability_policy", "warn")
        msg = (
            f"Pipeline missing required capabilities for profile '{self.profile.id}': "
            f"{sorted(missing)} (available: {sorted(available)})"
        )
        if policy == "fail":
            raise CapabilityError(msg)
        elif policy == "downgrade":
            logger.warning("Downgrading execution: %s", msg)
        else:
            logger.warning(msg)

    def execute(
        self,
        source_path: Path,
        from_stage: str | None = None,
        to_stage: str | None = None,
        only_stage: str | None = None,
    ) -> RunResult:
        """
        Execute the pipeline on a source file, with DAG stage filtering and locks.
        """
        source_path = source_path.resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Input robustness inspection
        from examforge.orchestrator.robustness import (
            InputRobustnessError,
            inspect_and_repair_input,
        )

        try:
            effective_path = inspect_and_repair_input(
                source_path, scratch_dir=self.runs_dir / "scratch"
            )
        except InputRobustnessError as exc:
            logger.error("Input robustness failure: %s", exc)
            return RunResult(
                run_id="input_error",
                run_dir=self.runs_dir,
                document=ExamDocument(source_path=str(source_path)),
                manifest=Manifest(run_id="input_error", source_path=str(source_path)),
                exit_code=getattr(exc, "exit_code", EXIT_FAILED),
                error=str(exc),
            )

        self.negotiate_capabilities()

        # Create run directory
        s_hash = _file_hash(effective_path) if effective_path.is_file() else "dir"
        run_id = _generate_run_id(paper_hash=s_hash)
        run_dir = RunDirectory(self.runs_dir, run_id)
        run_dir.create()

        from examforge.orchestrator.io import EventLogger, RunLock

        with RunLock(run_dir.root):
            event_logger = EventLogger(run_dir.root)
            event_logger.log_event("run_start", "pipeline", {"source": str(effective_path)})

            logger.info("Starting run %s for %s", run_id, effective_path.name)

            # Initialize document
            document = ExamDocument(
                source_path=str(effective_path),
                source_hash=s_hash,
            )

            from examforge.spec import compute_spec_hash

            spec_hash = compute_spec_hash(
                engine_version="2.0.0",
                profile=self.profile,
                enabled_rules=list(self.spec.rules.keys()),
                compute_tier=self.compute_tier.tier,
            )

            # Initialize manifest
            manifest = Manifest(
                run_id=run_id,
                source_path=str(effective_path),
                source_hash=document.source_hash,
                config_hash=_config_hash(self.config),
                spec_hash=spec_hash,
                mode=self.config.mode,
            )
            manifest.save(run_dir.manifest_path)

            # Resolve stages to execute via DAG
            stages_to_run = self.stages
            if from_stage or to_stage or only_stage:
                from examforge.orchestrator.dag import get_default_stage_dag

                dag = get_default_stage_dag()
                allowed_names = dag.resolve_order(
                    from_stage=from_stage,
                    to_stage=to_stage,
                    only_stage=only_stage,
                )
                stages_to_run = [s for s in self.stages if s.name in allowed_names]

            return self._run_stages(
                document=document,
                run_dir=run_dir,
                manifest=manifest,
                stages_to_run=stages_to_run,
                event_logger=event_logger,
            )

    def resume(self, run_id: str) -> RunResult:
        """
        Resume a previously interrupted run from the last completed stage.
        """
        run_dir = RunDirectory(self.runs_dir, run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir.root}")

        from examforge.orchestrator.io import EventLogger, RunLock

        with RunLock(run_dir.root):
            manifest = Manifest.load(run_dir.manifest_path)
            completed = manifest.get_completed_stage_names()
            event_logger = EventLogger(run_dir.root)

            from examforge.spec import compute_spec_hash

            current_spec_hash = compute_spec_hash(
                engine_version="2.0.0",
                profile=self.profile,
                enabled_rules=list(self.spec.rules.keys()),
                compute_tier=self.compute_tier.tier,
            )

            if manifest.spec_hash and manifest.spec_hash != current_spec_hash:
                logger.warning(
                    "Spec hash changed (%s != %s). Invalidating checkpoints and restarting.",
                    manifest.spec_hash,
                    current_spec_hash,
                )
                manifest.spec_hash = current_spec_hash
                document = run_dir.load_document()
                start_index = 0
            elif not completed:
                # Nothing completed — restart from the beginning
                document = run_dir.load_document()
                start_index = 0
            else:
                # Find the index of the next stage after the last completed one
                last = completed[-1]
                document = None
                for comp in reversed(completed):
                    try:
                        document = run_dir.load_document(stage_name=comp)
                        break
                    except FileNotFoundError:
                        continue
                if document is None:
                    document = run_dir.load_document()
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
            event_logger.log_event(
                "run_resume",
                self.stages[start_index].name,
                {"start_index": start_index},
            )

            return self._run_stages(
                document=document,
                run_dir=run_dir,
                manifest=manifest,
                stages_to_run=self.stages[start_index:],
                event_logger=event_logger,
            )

    def _run_stages(
        self,
        document: ExamDocument,
        run_dir: RunDirectory,
        manifest: Manifest,
        stages_to_run: list[Stage],
        event_logger: Any | None = None,
    ) -> RunResult:
        """Core loop: run stages in order, log events, and save checkpoints."""
        for stage in stages_to_run:
            stage_name = stage.name
            s_dir = run_dir.stage_dir(stage_name)
            s_dir.mkdir(parents=True, exist_ok=True)

            logger.info("-- Stage %s --", stage_name)
            manifest.record_stage_start(stage_name)
            manifest.save(run_dir.manifest_path)
            if event_logger:
                event_logger.log_event("stage_start", stage_name)

            ctx = StageContext(
                document=document,
                run_dir=run_dir.root,
                config=self.config,
                spec=self.spec,
                stage_dir=s_dir,
                profile=self.profile,
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
                if event_logger:
                    event_logger.log_event("stage_error", stage_name, {"error": error_msg})
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
                if event_logger:
                    event_logger.log_event("stage_error", stage_name, {"error": error_msg})
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
                    if event_logger:
                        event_logger.log_event("stage_error", stage_name, {"error": error_msg})
                    return RunResult(
                        run_id=manifest.run_id,
                        run_dir=run_dir.root,
                        document=document,
                        manifest=manifest,
                        exit_code=EXIT_FAILED,
                        error=error_msg,
                    )
                # fail_page / fail_warn: log and continue
                logger.warning(
                    "  [WARN] Continuing despite postcondition failure (policy=%s)",
                    self.config.fail_policy,
                )

            # Record success
            metrics = {**result.metrics, "elapsed_s": round(elapsed, 3)}
            manifest.record_stage_complete(
                stage_name,
                metrics=metrics,
                issue_count=len(result.issues),
            )

            # Checkpoint
            tier = getattr(self.config, "checkpoint_tier", "major")
            run_dir.save_document(document, stage_name, tier=tier)
            manifest.save(run_dir.manifest_path)
            if event_logger:
                event_logger.log_event("stage_complete", stage_name, metrics)

            logger.info(
                "  [OK] %s completed in %.1fs (%d issues)",
                stage_name,
                elapsed,
                len(result.issues),
            )

        # All stages complete: always ensure final document.json is saved
        run_dir.save_document(document, tier="all")
        exit_code = self._compute_exit_code(document, run_dir)
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

    def _compute_exit_code(
        self, document: ExamDocument, run_dir: RunDirectory | None = None
    ) -> int:
        """Determine exit code from document state and run outputs."""
        if run_dir and (run_dir.root / "review.html").exists():
            return EXIT_NEEDS_REVIEW

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
