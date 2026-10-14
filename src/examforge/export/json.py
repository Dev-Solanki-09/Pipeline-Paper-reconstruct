"""
Phase 14.6 — JSON IR Exporter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from examforge.export.base import BaseExporter
from examforge.ir.schema import ExamDocument


class JSONExporter(BaseExporter):
    """Exports ExamDocument IR as formatted, schema-compliant JSON."""

    format_name = "json"

    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        json_text = doc.model_dump_json(indent=2)
        output_path.write_text(json_text, encoding="utf-8")
        return output_path
