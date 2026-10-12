"""
Stage base class and context.

Every pipeline stage inherits from Stage and implements `run()`.
The runner calls stages sequentially, checking pre/post-conditions
around each invocation and saving checkpoints after success.

Design decisions:
- Stages are stateless: all mutable state lives in StageContext.document.
- Pre/post-conditions return violation messages (empty = pass).
- A failed post-condition on a blocker rule stops the run.
- Stages declare their name as a class attribute for manifest/checkpoint keys.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from examforge.ir.schema import ExamDocument, Issue

if TYPE_CHECKING:
    from examforge.config import ExamForgeConfig
    from examforge.spec import Spec

logger = logging.getLogger(__name__)


@dataclass
class StageContext:
    """
    Everything a stage needs to do its work.

    The document is the mutable IR state. The stage_dir is a pre-created
    directory for the stage's file outputs (page images, crops, etc.).
    """

    document: ExamDocument
    run_dir: Path
    config: ExamForgeConfig
    spec: Spec
    stage_dir: Path

    @property
    def mode(self) -> str:
        return self.config.mode

    @property
    def debug(self) -> bool:
        return self.config.debug


@dataclass
class StageResult:
    """
    What a stage returns after processing.

    The document is the updated IR state. Metrics are stage-specific
    measurements (timing, counts, scores). Issues are problems found.
    """

    document: ExamDocument
    metrics: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)


class Stage(ABC):
    """
    Abstract base class for all pipeline stages.

    Subclasses must set `name` and implement `run()`. Pre/post-conditions
    are optional but recommended for correctness enforcement.
    """

    name: str = "unnamed"

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult:
        """
        Execute the stage's processing logic.

        Args:
            ctx: The stage context with document, config, paths.

        Returns:
            StageResult with updated document, metrics, and issues.
        """
        ...

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """
        Check that the stage's prerequisites are met.

        Returns:
            List of violation messages. Empty list means all preconditions pass.
        """
        return []

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """
        Check that the stage's outputs satisfy invariants.

        Returns:
            List of violation messages. Empty list means all postconditions pass.
        """
        return []

    def __repr__(self) -> str:
        return f"<Stage: {self.name}>"
