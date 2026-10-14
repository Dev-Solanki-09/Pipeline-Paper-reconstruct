"""
Token-level LaTeX math delimiter wrapping with strict prose protection.
"""

from __future__ import annotations

import re

# LaTeX command pattern
_LATEX_COMMAND_RE = re.compile(r"(?:\\[a-zA-Z]+|\^{[^}]+}|_{[^}]+})")

# Known words allowed in mathematical text (like \text{ ...})
_LATEX_KNOWN_COMMANDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma",
    "tau", "upsilon", "phi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega",
    "times", "div", "pm", "mp", "le", "ge", "ne", "approx", "equiv",
    "propto", "infty", "partial", "nabla", "int", "sum", "prod",
    "in", "notin", "subset", "subseteq", "cup", "cap", "emptyset",
    "circ", "to", "implies", "rightleftharpoons", "leftrightarrow",
    "sqrt", "frac", "vec", "hat", "text", "ce",
}


def wrap_math_delimiters(text: str) -> str:
    """
    Wrap LaTeX mathematical expressions in $...$ delimiters for KaTeX rendering.

    Guarantees:
    - Never wraps isolated prose words (e.g. 'x', '2', 'm' in English prose).
    - Idempotent: wrap(wrap(x)) == wrap(x).
    - Preserves existing delimiters without double wrapping ($...$ or $$...$$).
    """
    if not text or not _LATEX_COMMAND_RE.search(text):
        return text

    stripped = text.strip()
    # Already wrapped in $ or $$
    if (stripped.startswith("$") and stripped.endswith("$")) or (
        stripped.startswith("$$") and stripped.endswith("$$")
    ):
        return text

    # Extract words that are not LaTeX commands
    cmd_names = set(re.findall(r"\\([a-zA-Z]+)", stripped))
    all_words = re.findall(r"\b[a-zA-Z]{2,}\b", stripped)
    prose_words = [w for w in all_words if w not in cmd_names and w not in _LATEX_KNOWN_COMMANDS]

    # Pure math formula: 0 or 1 prose words and has math commands / operators
    is_pure_math = len(prose_words) == 0 and (
        any(op in stripped for op in ["=", "<", ">", r"\times", r"\le", r"\ge", r"\to", r"\sqrt", r"\frac"])
        or stripped.startswith(r"\sqrt")
        or stripped.startswith(r"\frac")
    )

    if is_pure_math:
        return f"${stripped}$"

    # Mixed prose with inline math:
    # Wrap only formula expressions containing a LaTeX command or script
    def _replacer(match: re.Match) -> str:
        expr = match.group(0).strip()
        trailing = ""
        if expr.endswith((".", ",", ";", ":", "?", "!")):
            trailing = expr[-1]
            expr = expr[:-1].strip()
        return f"${expr}${trailing}"

    # Token in formula: LaTeX command, variable, number, or math operator
    # Formula token must be anchored by at least one explicit LaTeX command or script!
    math_sym = r"(?:\\[a-zA-Z]+|\b[a-zA-Z]\b|\d+(?:\.\d+)?|[\^_{}=+\-*/<>±×÷≈≠≤≥→←~|()[\]])"
    pattern = re.compile(
        rf"(?:{math_sym}\s*){{0,6}}"
        r"(?:\\[a-zA-Z]+|\^{[^}]+}|_{[^}]+})"
        rf"(?:\s*{math_sym}){{0,6}}"
    )

    # Split on $ to avoid re-wrapping anything already inside $...$
    parts = text.split("$")
    for i in range(0, len(parts), 2):  # Even indices are outside delimiters
        parts[i] = pattern.sub(_replacer, parts[i])

    res = "$".join(parts)
    # Clean up accidental double delimiters: $$...$$ if created by inline replacement
    res = re.sub(r"(?<!\$)\${2,}([^$]+)\${2,}(?!\$)", r"$\1$", res)
    return res
