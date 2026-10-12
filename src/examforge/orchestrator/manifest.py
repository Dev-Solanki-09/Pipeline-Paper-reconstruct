"""
Run manifest: the record of a pipeline execution.

The manifest captures everything needed to understand and reproduce a run:
source file, config/spec hashes, stage progression, timing, and exit status.
It is written atomically after each stage completes, so a crash mid-stage
leaves the manifest in a consistent state pointing to the last good checkpoint.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from examforge.ir.schema import PageStatus


class StageRecord(BaseModel):
    """Record of a single stage's execution."""

    name: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"  # "running", "completed", "failed", "skipped"
    metrics: dict = Field(default_factory=dict)
    issue_count: int = 0
    error: str | None = None


class Manifest(BaseModel):
    """
    Persistent record of a pipeline run.

    Written to manifest.json in the run directory. Updated atomically
    after each stage completes. Used by --resume to detect where to restart.
    """

    run_id: str
    source_path: str
    source_hash: str = ""
    config_hash: str = ""
    spec_hash: str = ""
    mode: str = "fast"

    # Timing
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None

    # Status
    status: str = "running"  # "running", "completed", "failed", "needs_review"
    exit_code: int | None = None

    # Stage tracking
    stages: list[StageRecord] = Field(default_factory=list)
    current_stage: str | None = None
    last_completed_stage: str | None = None

    # Page tracking
    page_statuses: dict[str, PageStatus] = Field(default_factory=dict)

    # Summary
    total_pages: int = 0
    total_questions: int = 0
    total_issues: int = 0
    blocker_count: int = 0

    def record_stage_start(self, name: str) -> None:
        """Record that a stage has started."""
        self.current_stage = name
        self.stages.append(StageRecord(name=name, started_at=datetime.now()))

    def record_stage_complete(
        self,
        name: str,
        metrics: dict | None = None,
        issue_count: int = 0,
    ) -> None:
        """Record that a stage completed successfully."""
        for stage in self.stages:
            if stage.name == name and stage.status == "running":
                stage.completed_at = datetime.now()
                stage.status = "completed"
                stage.metrics = metrics or {}
                stage.issue_count = issue_count
                break
        self.last_completed_stage = name
        self.current_stage = None

    def record_stage_failure(self, name: str, error: str) -> None:
        """Record that a stage failed."""
        for stage in self.stages:
            if stage.name == name and stage.status == "running":
                stage.completed_at = datetime.now()
                stage.status = "failed"
                stage.error = error
                break
        self.current_stage = None

    def get_completed_stage_names(self) -> list[str]:
        """Return names of all completed stages in order."""
        return [s.name for s in self.stages if s.status == "completed"]

    def save(self, path: Path) -> None:
        """Atomically write manifest to disk."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2))
        tmp.replace(path)  # atomic on POSIX, best-effort on Windows

    @classmethod
    def load(cls, path: Path) -> Manifest:
        """Load manifest from disk."""
        data = json.loads(path.read_text())
        return cls(**data)
