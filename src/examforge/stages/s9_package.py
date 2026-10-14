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

from examforge.export import get_exporter
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
    the IR as JSON, plus optional formats (Markdown, JSONL, QTI).
    """

    name = "s9_package"

    @classmethod
    def capabilities(cls) -> list[str]:
        return [
            "html_exporter",
            "json_exporter",
            "markdown_exporter",
            "jsonl_exporter",
            "qti_exporter",
        ]

    def run(self, ctx: StageContext) -> StageResult:
        issues: list[Issue] = []
        metrics: dict = {}

        doc = ctx.document

        # Ensure directories exist
        ctx.stage_dir.mkdir(parents=True, exist_ok=True)
        if ctx.run_dir:
            ctx.run_dir.mkdir(parents=True, exist_ok=True)

        # Output policy: default include_answers = False so question papers never leak keys
        include_answers = False
        config_answers = (
            ctx.config and hasattr(ctx.config, "flag") and ctx.config.flag("include_answers", False)
        )
        profile_answers = (
            ctx.resolved_profile
            and hasattr(ctx.resolved_profile, "output")
            and getattr(ctx.resolved_profile.output, "include_answers", False)
        )
        if config_answers or profile_answers:
            include_answers = True

        export_doc = doc
        has_answers = any(
            q.answer is not None or q.solution is not None for q in doc.questions
        )
        if not include_answers and has_answers:
            sanitized_questions = [
                q.model_copy(update={"answer": None, "solution": None})
                for q in doc.questions
            ]
            export_doc = doc.model_copy(update={"questions": sanitized_questions})

        # Render HTML
        html_path = ctx.stage_dir / "output.html"
        html_content = _render_html(export_doc, ctx)
        html_path.write_text(html_content, encoding="utf-8")
        if ctx.run_dir:
            (ctx.run_dir / "output.html").write_text(html_content, encoding="utf-8")
        metrics["html_size_bytes"] = len(html_content.encode("utf-8"))

        # Save IR as JSON
        ir_path = ctx.stage_dir / "document.json"
        ir_json = export_doc.model_dump_json(indent=2)
        ir_path.write_text(ir_json, encoding="utf-8")
        if ctx.run_dir:
            (ctx.run_dir / "document.json").write_text(ir_json, encoding="utf-8")
        metrics["ir_size_bytes"] = len(ir_json.encode("utf-8"))

        # Exporter selection
        active_exporters: set[str] = {"html", "json"}
        if (
            ctx.resolved_profile
            and hasattr(ctx.resolved_profile, "output")
            and getattr(ctx.resolved_profile.output, "exporters", None)
        ):
            active_exporters.update(ctx.resolved_profile.output.exporters)

        if (
            ctx.config
            and hasattr(ctx.config, "flag")
            and ctx.config.flag("exporters", default=False)
        ):
            active_exporters.update(["markdown", "jsonl", "qti"])

        # Run Markdown exporter if configured
        if "markdown" in active_exporters or "md" in active_exporters:
            md_exporter = get_exporter("markdown")
            md_path = ctx.stage_dir / "output.md"
            md_exporter.export(export_doc, md_path)
            if ctx.run_dir:
                md_exporter.export(export_doc, ctx.run_dir / "output.md")
            metrics["markdown_size_bytes"] = md_path.stat().st_size

        # Run JSONL exporter if configured
        if "jsonl" in active_exporters:
            jsonl_exporter = get_exporter("jsonl")
            jsonl_path = ctx.stage_dir / "questions.jsonl"
            jsonl_exporter.export(export_doc, jsonl_path)
            if ctx.run_dir:
                jsonl_exporter.export(export_doc, ctx.run_dir / "questions.jsonl")
            metrics["jsonl_size_bytes"] = jsonl_path.stat().st_size

        # Run QTI exporter if configured
        if "qti" in active_exporters:
            qti_exporter = get_exporter("qti")
            qti_path = ctx.stage_dir / "qti.xml"
            qti_exporter.export(export_doc, qti_path)
            if ctx.run_dir:
                qti_exporter.export(export_doc, ctx.run_dir / "qti.xml")
            metrics["qti_size_bytes"] = qti_path.stat().st_size

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
    from examforge.export.html import _jinja_zip
    from examforge.stages.s4_structure import get_option_packing_class

    env.filters["b64_image"] = _b64_image_filter(ctx)
    env.filters["option_packing_class"] = get_option_packing_class
    env.filters["zip"] = _jinja_zip

    template_name = "exam.html.j2"
    template_v2_active = (
        ctx.config and hasattr(ctx.config, "flag") and ctx.config.flag("template_v2", default=False)
    )
    if template_v2_active:
        template_name = "exam_v2.html.j2"

    if (
        ctx.resolved_profile
        and hasattr(ctx.resolved_profile, "output")
        and ctx.resolved_profile.output.template
    ):
        candidate_template = ctx.resolved_profile.output.template
        if not candidate_template.endswith(".j2"):
            candidate_template = f"{candidate_template}.html.j2"
        # Only override if profile explicitly requested a non-default template or flag off
        if not (template_v2_active and candidate_template == "exam.html.j2"):
            template_name = candidate_template

    template = env.get_template(template_name)

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
        tables=doc.tables,
        passages=doc.passages,
        pages=doc.pages,
        question_pages=question_pages,
        blocks=doc.blocks,
        issues=doc.issues,
        spec_hash=ctx.spec.hash() if ctx.spec else "",
        debug=ctx.debug,
        profile=ctx.resolved_profile,
    )

    return html


def _b64_image_filter(ctx: StageContext):
    """Jinja2 filter that converts an image path to a base64 data URI."""
    def _filter(rel_path: str | None) -> str:
        if not rel_path:
            return ""
        p = Path(rel_path)
        candidates = []
        if p.is_absolute():
            candidates.append(p)
        else:
            if ctx.run_dir:
                candidates.append(ctx.run_dir / rel_path)
                candidates.append(ctx.run_dir / "figures" / p.name)
                candidates.append(ctx.run_dir / "s6_figures" / p.name)
            if ctx.stage_dir:
                candidates.append(ctx.stage_dir / rel_path)
                candidates.append(ctx.stage_dir / "figures" / p.name)
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
