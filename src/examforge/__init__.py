"""ExamForge: Exam paper reconstruction pipeline."""

from examforge.config import ExamForgeConfig
from examforge.ir import ExamDocument
from examforge.orchestrator import PipelineRunner, RunResult
from examforge.spec import Rule, Spec

__version__ = "2.0.0"

__all__ = [
    "__version__",
    "ExamForgeConfig",
    "ExamDocument",
    "PipelineRunner",
    "RunResult",
    "Rule",
    "Spec",
]
