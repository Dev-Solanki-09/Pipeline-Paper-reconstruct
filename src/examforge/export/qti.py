"""
Phase 14.6 — QTI-Lite XML Exporter with Unsupported Sidecar Report.
"""

from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from examforge.export.base import BaseExporter
from examforge.ir.schema import ExamDocument, Question, QuestionKind

# Kinds directly expressible in QTI-lite
QTI_SUPPORTED_KINDS = {
    QuestionKind.SINGLE_CORRECT,
    QuestionKind.MULTI_CORRECT,
    QuestionKind.NUMERICAL,
}


class QTIExporter(BaseExporter):
    """
    Exports supported Question items into an IMS QTI-lite XML assessment document.
    Unsupported question kinds are captured in a sidecar report ('<name>_unsupported.json').
    """

    format_name = "qti"

    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        xml_text, unsupported_report = self.generate_qti(doc, **kwargs)

        output_path.write_text(xml_text, encoding="utf-8")

        # Sidecar report
        sidecar_path = output_path.parent / f"{output_path.stem}_unsupported.json"
        if not sidecar_path.name.startswith("qti_"):
            # Default to qti_unsupported.json if simple name
            sidecar_path = output_path.parent / "qti_unsupported.json"
        sidecar_path.write_text(
            json.dumps(unsupported_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return output_path

    def generate_qti(
        self,
        doc: ExamDocument,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]]:
        root = ET.Element(
            "assessmentTest",
            {
                "xmlns": "http://www.imsglobal.org/xsd/imsqti_v2p1",
                "identifier": doc.metadata.series_code or "EXAMFORGE_TEST",
                "title": doc.metadata.exam_name or "Exam Assessment",
            },
        )

        test_part = ET.SubElement(
            root, "testPart", {"identifier": "part_1", "navigationMode": "linear"}
        )
        section = ET.SubElement(
            test_part, "assessmentSection", {"identifier": "sec_1", "title": "Main Section"}
        )

        supported: list[Question] = []
        unsupported: list[dict[str, Any]] = []

        for q in doc.questions:
            if q.kind not in QTI_SUPPORTED_KINDS or q.children:
                reason = (
                    "Hierarchical sub-questions not supported in QTI-lite"
                    if q.children
                    else f"Question kind '{q.kind}' not supported in QTI-lite"
                )
                unsupported.append(
                    {
                        "id": q.id,
                        "number": q.number,
                        "kind": q.kind.value if hasattr(q.kind, "value") else str(q.kind),
                        "reason": reason,
                    }
                )
                continue

            item_elem = self._build_item_element(q)
            section.append(item_elem)
            supported.append(q)

        # XML indentation and string serialization
        ET.indent(root, space="  ")
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml_body = ET.tostring(root, encoding="utf-8").decode("utf-8")
        xml_text = xml_declaration + xml_body + "\n"

        unsupported_report = {
            "total_questions": len(doc.questions),
            "supported_count": len(supported),
            "unsupported_count": len(unsupported),
            "unsupported_questions": unsupported,
        }

        return xml_text, unsupported_report

    def _build_item_element(self, q: Question) -> ET.Element:
        item = ET.Element(
            "assessmentItem",
            {
                "identifier": q.id,
                "title": f"Question {q.number}",
                "adaptive": "false",
                "timeDependent": "false",
            },
        )

        # Response declaration
        resp_type = "single" if q.kind == QuestionKind.SINGLE_CORRECT else "multiple"
        if q.kind == QuestionKind.NUMERICAL:
            resp_type = "single"

        resp_decl = ET.SubElement(
            item,
            "responseDeclaration",
            {
                "identifier": "RESPONSE",
                "cardinality": resp_type,
                "baseType": "float" if q.kind == QuestionKind.NUMERICAL else "identifier",
            },
        )

        # Correct response if present
        if q.answer is not None:
            correct_opts = getattr(q.answer, "correct_options", [])
            num_val = getattr(q.answer, "numeric_value", None)
            if correct_opts or num_val is not None:
                corr_resp = ET.SubElement(resp_decl, "correctResponse")
                if correct_opts:
                    for opt in correct_opts:
                        v = ET.SubElement(corr_resp, "value")
                        v.text = str(opt)
                elif num_val is not None:
                    v = ET.SubElement(corr_resp, "value")
                    v.text = str(num_val)

        # Item body
        body = ET.SubElement(item, "itemBody")
        stem_div = ET.SubElement(body, "div", {"class": "q-stem"})
        stem_text = q.stem_text_en or q.stem_text_hi or f"Question {q.number}"
        stem_p = ET.SubElement(stem_div, "p")
        stem_p.text = html.escape(stem_text)

        # Interaction
        if q.kind in (QuestionKind.SINGLE_CORRECT, QuestionKind.MULTI_CORRECT):
            max_choices = "1" if q.kind == QuestionKind.SINGLE_CORRECT else str(len(q.options))
            interaction = ET.SubElement(
                body,
                "choiceInteraction",
                {
                    "responseIdentifier": "RESPONSE",
                    "shuffle": "false",
                    "maxChoices": max_choices,
                },
            )
            for opt in q.options:
                choice = ET.SubElement(
                    interaction,
                    "simpleChoice",
                    {"identifier": opt.label},
                )
                choice.text = html.escape(opt.text_str_en or opt.text_str_hi or opt.label)

        elif q.kind == QuestionKind.NUMERICAL:
            ET.SubElement(
                body,
                "extendedTextInteraction",
                {
                    "responseIdentifier": "RESPONSE",
                    "expectedLength": "10",
                },
            )

        return item
