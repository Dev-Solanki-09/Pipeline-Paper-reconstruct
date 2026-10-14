"""
Phase 14.6 — Exporter Base Protocol and Interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from examforge.ir.schema import ExamDocument


class BaseExporter(ABC):
    """Abstract base class for all ExamDocument exporters."""

    format_name: str

    @abstractmethod
    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        """Export document to output_path. Returns the resolved written path."""
