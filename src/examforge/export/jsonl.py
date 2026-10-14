"""
Phase 14.6 — JSONL Dataset / Bank Exporter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examforge.export.base import BaseExporter
from examforge.ir.schema import ExamDocument, Question


class JSONLExporter(BaseExporter):
    """Exports ExamDocument IR as newline-delimited JSON (JSONL), one question per line."""

    format_name = "jsonl"

    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        doc_meta = {
            "exam_name": doc.metadata.exam_name,
            "year": doc.metadata.year,
            "subject": doc.metadata.subject,
            "series_code": doc.metadata.series_code,
            "source_hash": doc.source_hash,
            "schema_version": doc.schema_version,
        }

        for q in doc.questions:
            item = self._serialize_question(q, doc_meta)
            lines.append(json.dumps(item, ensure_ascii=False))

        output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return output_path

    def _serialize_question(self, q: Question, doc_meta: dict[str, Any]) -> dict[str, Any]:
        marks_val = None
        if q.marks is not None:
            marks_val = q.marks.model_dump() if hasattr(q.marks, "model_dump") else q.marks

        answer_val = None
        if q.answer is not None:
            answer_val = q.answer.model_dump() if hasattr(q.answer, "model_dump") else q.answer

        sol_val = None
        if q.solution:
            sol_val = [node.model_dump() for node in q.solution]

        children_val = [self._serialize_question(c, doc_meta) for c in q.children]

        return {
            "id": q.id,
            "number": q.number,
            "section": q.section,
            "kind": q.kind.value if hasattr(q.kind, "value") else str(q.kind),
            "stem": [node.model_dump() for node in q.stem],
            "options": [opt.model_dump() for opt in q.options],
            "answer": answer_val,
            "solution": sol_val,
            "marks": marks_val,
            "figure_refs": q.figure_refs,
            "provenance": (
                q.provenance.value if hasattr(q.provenance, "value") else str(q.provenance)
            ),
            "children": children_val,
            "exam_metadata": doc_meta,
        }
