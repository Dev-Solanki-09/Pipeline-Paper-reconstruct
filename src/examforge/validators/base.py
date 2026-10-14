"""Base Validator protocol and helper classes for ExamForge specification rules."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity
from examforge.spec import Rule


class CostTier(StrEnum):
    """Execution cost tiers for validators (Phase O4.1)."""

    FREE = "free"    # Pure Python on the IR, zero extra IO/rendering, always run (< 5ms)
    IO = "io"        # Needs page rasters, image crops, or reading PDF text layer
    HEAVY = "heavy"  # Headless browser, external processes, or packaged HTML render checks


@runtime_checkable
class Validator(Protocol):
    """Protocol implemented by all rule validators."""

    id: str
    severity: IssueSeverity
    scope: Literal["question", "document"]
    capabilities: list[str]
    cost_tier: CostTier

    def check(self, doc: ExamDocument, ctx: Any | None = None) -> list[Issue]:
        """Execute validation check on document and return detected issues."""
        ...


class FunctionValidator:
    """Adapts a validator function to the Validator protocol."""

    def __init__(
        self,
        validator_id: str,
        func: Callable[[ExamDocument, Any], list[Issue]],
        severity: IssueSeverity = IssueSeverity.BLOCKER,
        scope: Literal["question", "document"] = "document",
        capabilities: list[str] | None = None,
        cost_tier: CostTier = CostTier.FREE,
    ):
        self.id = validator_id
        self.func = func
        self.severity = severity
        self.scope = scope
        self.capabilities = capabilities or ["validators"]
        self.cost_tier = cost_tier

    def check(self, doc: ExamDocument, ctx: Any | None = None) -> list[Issue]:
        return self.func(doc, ctx)

    def __call__(self, doc: ExamDocument, rule_or_ctx: Any = None) -> list[Issue]:
        return self.check(doc, rule_or_ctx)

