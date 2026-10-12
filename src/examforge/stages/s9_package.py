"""
S9 Package: final output generation.

Produces:
1. A single-file HTML document from the ExamDocument IR via Jinja2 templates
2. A JSON dump of the complete IR for programmatic access
3. A summary report with metrics and issue counts

Design decisions:
- Jinja2 templates are deterministic — agent never writes free-form HTML
- Math formulas are inline SVG (pre-rendered upstream in S5, M1 uses text fallback)
- Figures are embedded as base64 data URIs for single-file output
- @page margin: 0 to suppress browser-added headers/footers
- Bilingual 50/50 grid with break-inside: avoid on questions
- Stable IDs and sorted attributes for diffable output
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import jinja2

from examforge.ir.schema import (
    ExamDocument,
    Issue,
    IssueSeverity,
    PageClassification,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Path to templates directory, relative to this file
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class S9Package(Stage):
    """
    Stage 9: Package the final output.

    Renders the ExamDocument into a single HTML file and saves
    the IR as JSON. In M1, this produces a skeleton HTML showing
    the extracted page structure and metadata.
    """

    name = "s9_package"

    def run(self, ctx: StageContext) -> StageResult:
        issues: list[Issue] = []
        metrics: dict = {}

        doc = ctx.document

        # Ensure directories exist
        ctx.stage_dir.mkdir(parents=True, exist_ok=True)
        if ctx.run_dir:
            ctx.run_dir.mkdir(parents=True, exist_ok=True)

        # Render HTML
        html_path = ctx.stage_dir / "output.html"
        html_content = _render_html(doc, ctx)
        html_path.write_text(html_content, encoding="utf-8")
        if ctx.run_dir:
            (ctx.run_dir / "output.html").write_text(html_content, encoding="utf-8")
        metrics["html_size_bytes"] = len(html_content.encode("utf-8"))

        # Save IR as JSON
        ir_path = ctx.stage_dir / "document.json"
        ir_json = doc.model_dump_json(indent=2)
        ir_path.write_text(ir_json, encoding="utf-8")
        metrics["ir_size_bytes"] = len(ir_json.encode("utf-8"))

        # Generate summary report
        report = _generate_report(doc, metrics)
        report_path = ctx.stage_dir / "report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        logger.info(
            "  Packaged: HTML=%d bytes, IR=%d bytes",
            metrics["html_size_bytes"],
            metrics["ir_size_bytes"],
        )

        return StageResult(
            document=doc,
            metrics=metrics,
            issues=issues,
        )

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        violations = []
        if not ctx.document.pages:
            violations.append("No pages in document — S0 intake may not have run")
        return violations


def _render_html(doc: ExamDocument, ctx: StageContext) -> str:
    """Render the ExamDocument to HTML via Jinja2."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["b64_image"] = _b64_image_filter(ctx)

    template = env.get_template("exam.html.j2")

    # Prepare template context
    question_pages = [
        p for p in doc.pages
        if p.classification == PageClassification.QUESTIONS
    ]

    html = template.render(
        document=doc,
        metadata=doc.metadata,
        questions=doc.questions,
        figures=doc.figures,
        pages=doc.pages,
        question_pages=question_pages,
        blocks=doc.blocks,
        issues=doc.issues,
        spec_hash=ctx.spec.hash(),
        debug=ctx.debug,
    )

    return html


def _b64_image_filter(ctx: StageContext):
    """Jinja2 filter that converts an image path to a base64 data URI."""
    def _filter(rel_path: str | None) -> str:
        if not rel_path:
            return ""
        abs_path = ctx.run_dir / rel_path
        if not abs_path.exists():
            return ""
        data = abs_path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        # Detect format from extension
        suffix = abs_path.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{b64}"
    return _filter


def _generate_report(doc: ExamDocument, metrics: dict) -> dict:
    """Generate a summary report of the pipeline run."""
    blocker_issues = [i for i in doc.issues if i.severity == IssueSeverity.BLOCKER]
    warning_issues = [i for i in doc.issues if i.severity == IssueSeverity.WARNING]

    return {
        "summary": {
            "total_pages": len(doc.pages),
            "question_pages": sum(
                1 for p in doc.pages
                if p.classification == PageClassification.QUESTIONS
            ),
            "total_questions": len(doc.questions),
            "total_figures": len(doc.figures),
            "total_tables": len(doc.tables),
        },
        "metadata": doc.metadata.model_dump(),
        "issues": {
            "total": len(doc.issues),
            "blockers": len(blocker_issues),
            "warnings": len(warning_issues),
            "details": [i.model_dump() for i in doc.issues[:50]],  # Cap at 50
        },
        "page_summary": [
            {
                "page": p.page_number,
                "classification": p.classification.value,
                "has_text": p.has_text_layer,
                "text_valid": p.text_layer_valid,
                "dpi": p.dpi,
                "blur": p.blur_score,
            }
            for p in doc.pages
        ],
        "metrics": metrics,
    }
