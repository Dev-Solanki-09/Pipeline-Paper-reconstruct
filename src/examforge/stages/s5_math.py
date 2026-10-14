"""
S5 Math: Formula Handling & Unicode-to-LaTeX Conversion.

Converts Unicode mathematical symbols, superscripts, subscripts,
and Greek letters into LaTeX expressions, and formats them with
KaTeX-compatible delimiters ($...$ and $$...$$).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from examforge.ir.schema import (
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    Issue,
    IssueSeverity,
    Question,
)
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)

# Complete Unicode Math to LaTeX character map
UNICODE_TO_LATEX = {
    # Superscripts
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}", "⁴": "^{4}",
    "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}", "⁸": "^{8}", "⁹": "^{9}",
    "⁺": "^{+}", "⁻": "^{-}", "⁼": "^{=}", "⁽": "^{(}", "⁾": "^{)}", "ⁿ": "^{n}",
    # Subscripts
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}", "₄": "_{4}",
    "₅": "_{5}", "₆": "_{6}", "₇": "_{7}", "₈": "_{8}", "₉": "_{9}",
    "₊": "_{+}", "₋": "_{-}", "₌": "_{=}", "₍": "_{(}", "₎": "_{)}",
    # Greek lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "µ": r"\mu", "ν": r"\nu", "ξ": r"\xi",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    # Greek uppercase
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi",
    "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    # Operators & Relations
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "≤": r"\le", "≥": r"\ge", "≠": r"\ne", "≈": r"\approx", "≡": r"\equiv",
    "∝": r"\propto", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla",
    "∫": r"\int", "∑": r"\sum", "∏": r"\prod",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "∪": r"\cup", "∩": r"\cap", "∅": r"\emptyset",
    "°": r"^{\circ}", "′": r"'", "″": r"''",
    "→": r"\to", "⇒": r"\implies", "⇌": r"\rightleftharpoons", "↔": r"\leftrightarrow",
}

# Regex to detect LaTeX math commands
_LATEX_COMMAND_RE = re.compile(
    r"(?:\\[a-zA-Z]+|\^{[^}]+}|_{[^}]+})"
)


def convert_unicode_math(text: str) -> str:
    """Convert Unicode math characters, superscripts, and Greek letters to LaTeX."""
    if not text:
        return text

    # Handle square roots with parenthesis: √(expr) -> \sqrt{expr}
    text = re.sub(r"√\(([^)]+)\)", r"\\sqrt{\1}", text)
    # Handle square root with single variable/token: √2, √g
    text = re.sub(r"√([a-zA-Z0-9]+)", r"\\sqrt{\1}", text)
    # Standalone root
    text = text.replace("√", r"\sqrt{}")

    # Replace mapped Unicode characters
    for u_char, latex_str in UNICODE_TO_LATEX.items():
        if u_char in text:
            text = text.replace(u_char, latex_str)

    # Combine adjacent scripts: ^{2}^{3} -> ^{23}, _{1}_{2} -> _{12}
    while re.search(r"\^{([^}]+)}\^{([^}]+)}", text):
        text = re.sub(r"\^{([^}]+)}\^{([^}]+)}", r"^{\1\2}", text)
    while re.search(r"_{([^}]+)}_{([^}]+)}", text):
        text = re.sub(r"_{([^}]+)}_{([^}]+)}", r"_{\1\2}", text)

    return text


def wrap_math_delimiters(text: str) -> str:
    """
    Wrap LaTeX mathematical expressions in $...$ delimiters for KaTeX rendering.

    Avoids double wrapping if already enclosed in $...$ or $$...$$.
    """
    if not text or not _LATEX_COMMAND_RE.search(text):
        return text

    # If text is already wrapped in $...$ or $$...$$, return as-is
    stripped = text.strip()
    if (stripped.startswith("$") and stripped.endswith("$")) or (
        stripped.startswith("$$") and stripped.endswith("$$")
    ):
        return text

    # If the entire text contains no multi-letter words (excluding LaTeX commands)
    # and has math commands, it is a pure formula -> wrap entirely in $...$
    words = [
        w for w in re.findall(r"[a-zA-Z]+", stripped)
        if not any(cmd.endswith(w) for cmd in re.findall(r"\\[a-zA-Z]+", stripped))
    ]
    is_pure_math = len(words) <= 2 and (
        any(op in stripped for op in ["=", "<", ">", r"\times", r"\le", r"\ge", r"\to", r"\sqrt"])
        or stripped.startswith(r"\sqrt")
    )

    if is_pure_math:
        return f"${stripped}$"

    # For mixed prose with math terms:
    # Wrap isolated formulas containing math commands without capturing prose words
    # e.g., "where \theta = 30^{\circ} is angle" -> "where $\theta = 30^{\circ}$ is angle"
    def _replacer(match: re.Match) -> str:
        expr = match.group(0).strip()
        trailing = ""
        if expr.endswith((".", ",", ";", ":")):
            trailing = expr[-1]
            expr = expr[:-1].strip()
        return f"${expr}${trailing}"

    # Math token: single-letter variable, number, operator, LaTeX command, or subscript/superscript
    math_token = r"(?:\\[a-zA-Z]+|\b[a-zA-Z]\b|\d+(?:\.\d+)?|[\^_{}=+\-*/<>±×÷≈≠≤≥→←~|()[\]])"
    pattern = re.compile(
        rf"(?:{math_token}\s*){{0,6}}"
        r"(?:\\[a-zA-Z]+|\^{[^}]+}|_{[^}]+})"
        rf"(?:\s*{math_token}){{0,6}}"
    )

    # Avoid replacing if already inside $
    parts = text.split("$")
    for i in range(0, len(parts), 2):  # Even indices are outside $...$
        parts[i] = pattern.sub(_replacer, parts[i])

    res = "$".join(parts)
    # Clean up accidental double delimiters: $$...$$
    res = re.sub(r"\${2,}([^$]+)\${2,}", r"$\1$", res)
    return res


def format_math(text: str) -> str:
    """Complete math formatting pipeline for a text string."""
    if not text:
        return text
    converted = convert_unicode_math(text)
    return wrap_math_delimiters(converted)


def check_balanced_delimiters(text: str) -> bool:
    """Verify that $ delimiters and {} braces are balanced."""
    if not text:
        return True

    # Check dollar signs
    dollar_count = text.count("$")
    if dollar_count % 2 != 0:
        return False

    # Check braces
    brace_depth = 0
    for char in text:
        if char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth < 0:
                return False

    return brace_depth == 0


def format_math_v2(text: str) -> tuple[str, list[Issue]]:
    """Format math and chemistry using v2 notation pipeline and validate equations."""
    from examforge.notation.chemistry import (
        format_chemical_reaction,
        is_chemical_equation,
        validate_chemical_equation,
    )
    from examforge.notation.tokenizer import tokenize_and_convert_math
    from examforge.notation.wrapping import wrap_math_delimiters

    issues: list[Issue] = []
    if not text:
        return text, issues

    converted = tokenize_and_convert_math(text)

    # Validate chemical reactions if present (Rule R07)
    if is_chemical_equation(converted):
        is_balanced, balance_issues = validate_chemical_equation(converted)
        for b_iss in balance_issues:
            issues.append(
                Issue(
                    stage="s5_math",
                    rule_id="R07",
                    severity=IssueSeverity.WARNING,
                    message=f"Chemical equation balance issue: {b_iss}",
                )
            )
        converted = format_chemical_reaction(converted)

    wrapped = wrap_math_delimiters(converted)
    return wrapped, issues


class S5Math(Stage):
    """
    Stage 5: Detect formulas, convert Unicode math to LaTeX, and wrap in KaTeX delimiters.
    """

    name = "s5_math"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["math_latex", "formula_wrap"]

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S5 requires blocks to be present in the document."""
        violations = []
        if not ctx.document.blocks:
            violations.append("No blocks found in document — S3 Parse must run first.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict = {}

        use_v2 = bool(ctx.config and ctx.config.flag("lang_v2", default=False))
        formulas_converted = 0

        def _process_text(txt: str) -> str:
            nonlocal formulas_converted
            if not txt:
                return txt
            if use_v2:
                formatted, new_issues = format_math_v2(txt)
                issues.extend(new_issues)
            else:
                formatted = format_math(txt)

            if formatted != txt:
                formulas_converted += 1
            return formatted

        # 1. Process blocks
        for b in doc.blocks:
            if b.status == BlockStatus.DROPPED:
                continue

            orig_text = b.text
            formatted_text = _process_text(orig_text)

            if formatted_text != orig_text:
                b.text = formatted_text
                if _LATEX_COMMAND_RE.search(formatted_text) and len(b.text.split()) < 10:
                    b.type = BlockType.FORMULA

        # 2. Process questions
        for q in doc.questions:
            # Process stem blocks
            for b in q.stem_en + q.stem_hi:
                b.text = _process_text(b.text)

            # Process convenience strings
            if q.stem_text_en:
                q.stem_text_en = _process_text(q.stem_text_en)
            if q.stem_text_hi:
                q.stem_text_hi = _process_text(q.stem_text_hi)

            # Process options
            for opt in q.options:
                for b in opt.text_en + opt.text_hi:
                    b.text = _process_text(b.text)
                if opt.text_str_en:
                    opt.text_str_en = _process_text(opt.text_str_en)
                if opt.text_str_hi:
                    opt.text_str_hi = _process_text(opt.text_str_hi)

        metrics["formulas_converted"] = formulas_converted

        logger.info(
            "  S5 Math complete: converted %d formula / math expressions to LaTeX (v2=%s)",
            formulas_converted,
            use_v2,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Verify delimiter balance across questions and blocks."""
        violations = []
        for q in result.document.questions:
            for b in q.stem_en + q.stem_hi:
                if not check_balanced_delimiters(b.text):
                    violations.append(f"Question {q.id} stem block {b.id} has unbalanced math delimiters: {b.text[:40]}")
            for opt in q.options:
                for b in opt.text_en + opt.text_hi:
                    if not check_balanced_delimiters(b.text):
                        violations.append(f"Question {q.id} option {opt.label} has unbalanced delimiters: {b.text[:40]}")
        return violations
