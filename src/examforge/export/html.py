"""
Phase 14.6 — HTML Document Exporter.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import jinja2

from examforge.export.base import BaseExporter
from examforge.ir.schema import ExamDocument, PageClassification
from examforge.stages.s4_structure import get_option_packing_class

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _jinja_zip(a: Any, b: Any) -> list[tuple[Any, Any]]:
    import itertools

    return list(itertools.zip_longest(a or [], b or [], fillvalue={}))


class HTMLExporter(BaseExporter):
    """Exports ExamDocument IR as a self-contained HTML document via Jinja2."""

    format_name = "html"

    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        template_name: str | None = None,
        figures_dir: Path | None = None,
        **kwargs: Any,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = self.render_to_html(
            doc,
            template_name=template_name,
            figures_dir=figures_dir,
            output_dir=output_path.parent,
            **kwargs,
        )
        output_path.write_text(html_content, encoding="utf-8")
        return output_path

    def render_to_html(
        self,
        doc: ExamDocument,
        template_name: str | None = None,
        figures_dir: Path | None = None,
        output_dir: Path | None = None,
        **kwargs: Any,
    ) -> str:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=jinja2.select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        env.filters["b64_image"] = self._create_b64_filter(figures_dir, output_dir)
        env.filters["option_packing_class"] = get_option_packing_class
        env.filters["zip"] = _jinja_zip

        chosen_template = template_name or kwargs.get("template") or "exam_v2.html.j2"
        # If template does not exist, fallback to exam.html.j2
        if not (TEMPLATES_DIR / chosen_template).exists():
            chosen_template = "exam.html.j2"

        template = env.get_template(chosen_template)

        question_pages = [
            p for p in doc.pages if p.classification == PageClassification.QUESTIONS
        ]

        return template.render(
            document=doc,
            metadata=doc.metadata,
            questions=doc.questions,
            figures=doc.figures,
            tables=doc.tables,
            passages=doc.passages,
            pages=doc.pages,
            question_pages=question_pages,
            blocks=doc.blocks,
            issues=doc.issues,
            spec_hash=kwargs.get("spec_hash", ""),
            debug=kwargs.get("debug", False),
            profile=kwargs.get("profile"),
        )

    def _create_b64_filter(self, figures_dir: Path | None, output_dir: Path | None):
        def _filter(rel_path: str | None) -> str:
            if not rel_path:
                return ""
            p = Path(rel_path)
            candidates: list[Path] = []
            if p.is_absolute():
                candidates.append(p)
            else:
                if figures_dir:
                    candidates.append(figures_dir / rel_path)
                    candidates.append(figures_dir / p.name)
                if output_dir:
                    candidates.append(output_dir / rel_path)
                    candidates.append(output_dir / "figures" / p.name)
                cwd = Path.cwd()
                candidates.append(cwd / rel_path)
                candidates.append(cwd / "figures" / p.name)
                candidates.append(cwd / "output" / rel_path)
                candidates.append(p)

            abs_path = None
            for cand in candidates:
                if cand.exists() and cand.is_file():
                    abs_path = cand
                    break

            if not abs_path:
                return ""
            data = abs_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            suffix = abs_path.suffix.lower()
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }.get(suffix, "image/png")
            return f"data:{mime};base64,{b64}"

        return _filter
