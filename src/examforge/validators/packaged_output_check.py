"""
Consolidated Validator: packaged_output_check (Phase O4.2).

Merges R04 (continuous flow & no page wrappers) and R13 (render integrity, LaTeX/KaTeX syntax, image payloads)
into a unified packaged render verification check.
CostTier: HEAVY.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
import re
from typing import Any

from PIL import Image

from examforge.ir.schema import ExamDocument, FigureNode, Issue, IssueSeverity, MathNode
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

logger = logging.getLogger(__name__)

# Detect forbidden page-wrapper classes or page break artifacts inside question text
PAGE_WRAPPER_PATTERNS = [
    re.compile(r'class\s*=\s*["\'][^"\']*\b(?:page-wrapper|page_container|page-break|print-page)\b', re.IGNORECASE),
    re.compile(r'page-break-(?:before|after)\s*:\s*always', re.IGNORECASE),
    re.compile(r'<div[^>]+id=["\']page-\d+["\']', re.IGNORECASE),
]


def _check_latex_syntax(latex: str) -> list[str]:
    """Check for basic syntax errors in LaTeX strings without an external browser engine."""
    errors = []
    # 1. Balanced curly braces (ignoring escaped ones)
    cleaned = re.sub(r"\\[{}]", "", latex)
    open_count = cleaned.count("{")
    close_count = cleaned.count("}")
    if open_count != close_count:
        errors.append(f"Unbalanced braces: {open_count} '{{' vs {close_count} '}}'")

    # 2. Balanced environments \begin{xyz} ... \end{xyz}
    begins = re.findall(r"\\begin\{([a-zA-Z*]+)\}", latex)
    ends = re.findall(r"\\end\{([a-zA-Z*]+)\}", latex)
    if begins != ends:
        errors.append(f"Mismatched environments: \\begin{begins} vs \\end{ends}")

    # 3. Known KaTeX error patterns
    if re.search(r"\\frac\s*(?:$|[^\s{0-9a-zA-Z])", latex):
        if latex.strip() == r"\frac":
            errors.append("Incomplete \\frac command without arguments")

    return errors


def _validate_image_payload(data_str: str) -> tuple[bool, str, int, int]:
    """Validate base64 image or file reference, returning (is_valid, error_msg, width, height)."""
    if not data_str:
        return False, "Empty image data", 0, 0

    if data_str.startswith("data:image/"):
        try:
            _, b64data = data_str.split(",", 1)
            raw = base64.b64decode(b64data)
            img = Image.open(io.BytesIO(raw))
            w, h = img.size
            if w <= 0 or h <= 0:
                return False, f"Invalid dimensions: {w}x{h}", w, h
            return True, "", w, h
        except Exception as e:
            return False, f"Malformed base64 image: {e}", 0, 0

    # Local file path
    p = Path(data_str)
    if p.exists() and p.is_file():
        try:
            img = Image.open(p)
            w, h = img.size
            return True, "", w, h
        except Exception as e:
            return False, f"Unreadable image file {data_str}: {e}", 0, 0

    # If it's a ref like 'fig_1_1', check document figures
    return True, "", 100, 100


@register_validator(
    "packaged_output_check",
    cost_tier=CostTier.HEAVY,
    aliases=["no_page_wrappers_or_breaks", "render_check"],
)
def validate_packaged_output(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """
    Consolidated verification of:
    1. Continuous flow (no artificial page breaks, non-empty questions) [R04].
    2. Render integrity: LaTeX/KaTeX syntax and image payloads [R13].
    """
    issues: list[Issue] = []
    severity = (
        IssueSeverity.BLOCKER
        if (rule and getattr(rule.severity, "value", str(rule.severity)) == "blocker")
        else IssueSeverity.WARNING
    )
    rule_name = rule.check if rule and rule.check else "packaged_output_check"

    run_continuous = rule_name in ("packaged_output_check", "no_page_wrappers_or_breaks")
    run_render = rule_name in ("packaged_output_check", "render_check")

    # 1. R04 Check: Continuous flow
    if run_continuous:
        question_pages = [p for p in document.pages if getattr(p.classification, "value", str(p.classification)) == "questions"]
        if question_pages and not document.questions:
            issues.append(
                Issue(
                    id="r04_empty_questions",
                    stage="s8_verify",
                    rule="no_page_wrappers_or_breaks" if rule_name == "no_page_wrappers_or_breaks" else "packaged_output_check",
                    severity=severity,
                    message="Rule R04 violation: Continuous flow has no questions extracted",
                )
            )

    # 2. R13 Check: Render integrity
    if not run_render:
        return issues
    # 2a. MathNode LaTeX syntax
    for q in document.questions:
        for node in q.stem:
            if isinstance(node, MathNode):
                latex_errs = _check_latex_syntax(node.code)
                for err in latex_errs:
                    issues.append(
                        Issue(
                            id=f"r13_latex_{q.id}_{abs(hash(node.code)) % 10000}",
                            stage="s8_verify",
                            rule="render_check" if rule_name == "render_check" else "packaged_output_check",
                            question_id=q.id,
                            severity=severity,
                            message=f"Rule R13: LaTeX syntax error in Question {q.number}: {err}",
                            evidence={"latex": node.code[:100], "error": err},
                        )
                    )

        # 2b. Figure payloads and dimensions
        for node in q.stem:
            if isinstance(node, FigureNode):
                crop = node.figure_ref
                fig_obj = next((f for f in document.figures if f.id == node.figure_ref), None)
                if fig_obj and fig_obj.crop_path:
                    crop = fig_obj.crop_path

                is_valid, err_msg, w, h = _validate_image_payload(crop)
                if not is_valid:
                    issues.append(
                        Issue(
                            id=f"r13_figure_{q.id}",
                            stage="s8_verify",
                            rule=rule_name,
                            question_id=q.id,
                            severity=severity,
                            message=f"Rule R13: Broken figure payload in Question {q.number}: {err_msg}",
                            evidence={"ref": node.figure_ref[:60], "error": err_msg},
                        )
                    )

        # 2c. Page-wrapper check in raw question text / stem
        for pat in PAGE_WRAPPER_PATTERNS:
            if pat.search(q.stem_text_en):
                issues.append(
                    Issue(
                        id=f"r13_wrapper_{q.id}",
                        stage="s8_verify",
                        rule=rule_name,
                        question_id=q.id,
                        severity=severity,
                        message=f"Rule R13: Question {q.number} stem contains forbidden page-wrapper / break artifact",
                        evidence={"match": pat.pattern},
                    )
                )

    return issues
