"""
Phase 14.6 — GitHub-Flavored Markdown Exporter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from examforge.export.base import BaseExporter
from examforge.ir.schema import (
    BlankNode,
    CodeNode,
    ContentNode,
    ExamDocument,
    FigureNode,
    Marks,
    MatchColumnsNode,
    MathNode,
    Option,
    Question,
    RawCropNode,
    StatementsNode,
    TableNode,
    TextNode,
)


class MarkdownExporter(BaseExporter):
    """Exports ExamDocument IR as GitHub-Flavored Markdown (GFM)."""

    format_name = "markdown"

    def export(
        self,
        doc: ExamDocument,
        output_path: Path,
        **kwargs: Any,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        md_text = self.render_to_markdown(doc, **kwargs)
        output_path.write_text(md_text, encoding="utf-8")
        return output_path

    def render_to_markdown(self, doc: ExamDocument, **kwargs: Any) -> str:
        lines: list[str] = []

        # Document Header
        title = doc.metadata.exam_name or "Exam Paper"
        lines.append(f"# {title}")
        lines.append("")

        meta_parts: list[str] = []
        if doc.metadata.year:
            meta_parts.append(f"**Year:** {doc.metadata.year}")
        if doc.metadata.subject:
            meta_parts.append(f"**Subject:** {doc.metadata.subject}")
        if doc.metadata.series_code:
            meta_parts.append(f"**Series:** {doc.metadata.series_code}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
            lines.append("")

        current_section: str | None = None

        # Questions
        for q in doc.questions:
            if q.section and q.section != current_section:
                current_section = q.section
                lines.append(f"## Section: {current_section}")
                lines.append("")

            lines.extend(self._render_question(q))
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def _render_question(self, q: Question, level: int = 3) -> list[str]:
        lines: list[str] = []
        hashes = "#" * level
        lines.append(f"{hashes} Question {q.number}")

        if q.marks:
            if isinstance(q.marks, Marks):
                lines.append(f"*Marks: +{q.marks.positive} / -{q.marks.negative}*")
            else:
                lines.append(f"*Marks: {q.marks}*")
            lines.append("")

        # Question Stem
        stem_md = self._render_nodes(q.stem)
        if stem_md:
            lines.append(stem_md)
            lines.append("")

        # Options
        if q.options:
            for opt in q.options:
                opt_str = self._render_option(opt)
                lines.append(f"- **({opt.label})** {opt_str}")
            lines.append("")

        # Children (subparts)
        for child in q.children:
            lines.extend(self._render_question(child, level=level + 1))

        # Answer & Solution
        if q.answer is not None:
            ans_str = ""
            if getattr(q.answer, "correct_options", None):
                ans_str = ", ".join(q.answer.correct_options)
            elif getattr(q.answer, "numeric_value", None) is not None:
                ans_str = str(q.answer.numeric_value)
            if ans_str:
                lines.append(f"**Answer:** {ans_str}")
                lines.append("")

        if q.solution:
            sol_md = self._render_nodes(q.solution)
            if sol_md:
                lines.append(f"**Solution:**\n\n{sol_md}")
                lines.append("")

        return lines

    def _render_option(self, opt: Option) -> str:
        if opt.content:
            return self._render_nodes(opt.content).strip()
        if opt.text_str_en and opt.text_str_hi:
            return f"{opt.text_str_en} / *{opt.text_str_hi}*"
        return opt.text_str_en or opt.text_str_hi or ""

    def _render_nodes(self, nodes: list[ContentNode]) -> str:
        rendered: list[str] = []
        for node in nodes:
            if isinstance(node, TextNode):
                en = node.texts.get("en", "")
                hi = node.texts.get("hi", "")
                if en and hi:
                    rendered.append(f"{en}\n\n*{hi}*")
                elif en:
                    rendered.append(en)
                elif hi:
                    rendered.append(hi)
                elif node.texts:
                    rendered.append(next(iter(node.texts.values())))

            elif isinstance(node, MathNode):
                if node.display:
                    rendered.append(f"\n$$\n{node.code}\n$$\n")
                else:
                    rendered.append(f"${node.code}$")

            elif isinstance(node, TableNode):
                rendered.append(self._render_table(node))

            elif isinstance(node, FigureNode):
                caption = node.caption.get("en", "") or node.caption.get("hi", "") or "Figure"
                rendered.append(f"![{caption}]({node.figure_ref})")

            elif isinstance(node, StatementsNode):
                stmt_lines: list[str] = []
                for item in node.items:
                    for k, v in item.items():
                        stmt_lines.append(f"- **({k})** {v}")
                rendered.append("\n".join(stmt_lines))

            elif isinstance(node, MatchColumnsNode):
                col_lines = ["| Column I | Column II |", "|---|---|"]
                max_len = max(len(node.left), len(node.right)) if (node.left or node.right) else 0
                for i in range(max_len):
                    l_val = self._dict_first_val(node.left[i]) if i < len(node.left) else ""
                    r_val = self._dict_first_val(node.right[i]) if i < len(node.right) else ""
                    col_lines.append(f"| {l_val} | {r_val} |")
                rendered.append("\n".join(col_lines))

            elif isinstance(node, CodeNode):
                lang = node.language or ""
                rendered.append(f"```{lang}\n{node.text}\n```")

            elif isinstance(node, BlankNode):
                rendered.append(f"___({node.index})___")

            elif isinstance(node, RawCropNode):
                rendered.append(f"![Crop: {node.reason}]({node.figure_ref})")

        return "\n\n".join(r for r in rendered if r.strip())

    def _render_table(self, table: TableNode) -> str:
        if not table.rows:
            return ""
        table_lines: list[str] = []
        header_count = max(table.header_rows, 1)

        # First row as header
        header_cells = [c.text.replace("\n", " ").strip() for c in table.rows[0]]
        table_lines.append("| " + " | ".join(header_cells) + " |")
        table_lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

        for row in table.rows[header_count:]:
            cells = [c.text.replace("\n", " ").strip() for c in row]
            # Pad row if uneven
            if len(cells) < len(header_cells):
                cells.extend([""] * (len(header_cells) - len(cells)))
            table_lines.append("| " + " | ".join(cells[: len(header_cells)]) + " |")

        return "\n".join(table_lines)

    @staticmethod
    def _dict_first_val(d: dict[str, str]) -> str:
        if not d:
            return ""
        k, v = next(iter(d.items()))
        return f"({k}) {v}"
