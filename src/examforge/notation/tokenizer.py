"""
Notation Tokenizer: Unicode math symbols, scripts, Greek, units, vectors to LaTeX.
"""

from __future__ import annotations

import re

# Superscript and subscript character maps
_SUPERSCRIPTS = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")", "ⁿ": "n",
}

_SUBSCRIPTS = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
}

# Greek letters
_GREEK_LOWER = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "µ": r"\mu", "ν": r"\nu", "ξ": r"\xi",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
}

_GREEK_UPPER = {
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi",
    "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}

# Math operators & symbols
_MATH_OPERATORS = {
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "≤": r"\le", "≥": r"\ge", "≠": r"\ne", "≈": r"\approx", "≡": r"\equiv",
    "∝": r"\propto", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla",
    "∫": r"\int", "∑": r"\sum", "∏": r"\prod",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "∪": r"\cup", "∩": r"\cap", "∅": r"\emptyset",
    "°": r"^{\circ}", "′": r"'", "″": r"''",
    "→": r"\to", "⇒": r"\implies", "⇌": r"\rightleftharpoons", "↔": r"\leftrightarrow",
}

# Vulgar fractions
_VULGAR_FRACTIONS = {
    "½": r"\frac{1}{2}", "⅓": r"\frac{1}{3}", "⅔": r"\frac{2}{3}",
    "¼": r"\frac{1}{4}", "¾": r"\frac{3}{4}", "⅕": r"\frac{1}{5}",
    "⅖": r"\frac{2}{5}", "⅗": r"\frac{3}{5}", "⅘": r"\frac{4}{5}",
    "⅙": r"\frac{1}{6}", "⅚": r"\frac{5}{6}", "⅛": r"\frac{1}{8}",
    "⅜": r"\frac{3}{8}", "⅝": r"\frac{5}{8}", "⅞": r"\frac{7}{8}",
}

# Scientific units recognized for LaTeX \text{ ...} wrapping
_UNIT_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s+([a-zA-Z]+(?:\s*[a-zA-Z]+|\/[a-zA-Z]+|\^[-+]?\d+|\^{-?\d+})*)\b"
)


def convert_unicode_super_sub(text: str) -> str:
    """Convert Unicode superscripts and subscripts to LaTeX ^{...} and _{...}."""
    if not text:
        return text

    # Group consecutive superscripts
    def _repl_super(m: re.Match) -> str:
        s = m.group(0)
        return "^{" + "".join(_SUPERSCRIPTS.get(c, c) for c in s) + "}"

    # Group consecutive subscripts
    def _repl_sub(m: re.Match) -> str:
        s = m.group(0)
        return "_{" + "".join(_SUBSCRIPTS.get(c, c) for c in s) + "}"

    super_chars = "".join(_SUPERSCRIPTS.keys())
    sub_chars = "".join(_SUBSCRIPTS.keys())

    text = re.sub(f"[{re.escape(super_chars)}]+", _repl_super, text)
    text = re.sub(f"[{re.escape(sub_chars)}]+", _repl_sub, text)

    # Combine adjacent scripts if any: ^{a}^{b} -> ^{ab}
    while re.search(r"\^{([^}]+)}\^{([^}]+)}", text):
        text = re.sub(r"\^{([^}]+)}\^{([^}]+)}", r"^{\1\2}", text)
    while re.search(r"_{([^}]+)}_{([^}]+)}", text):
        text = re.sub(r"_{([^}]+)}_{([^}]+)}", r"_{\1\2}", text)

    return text


def convert_unicode_fractions(text: str) -> str:
    """Convert Unicode vulgar fractions to LaTeX \frac{a}{b}."""
    if not text:
        return text
    for u_frac, latex_frac in _VULGAR_FRACTIONS.items():
        if u_frac in text:
            text = text.replace(u_frac, latex_frac)
    return text


def convert_greek_letters(text: str) -> str:
    """Convert Unicode Greek letters to LaTeX commands."""
    if not text:
        return text
    for g_char, l_cmd in _GREEK_LOWER.items():
        if g_char in text:
            text = re.sub(rf"{re.escape(g_char)}(?=[a-zA-Z])", lambda m, cmd=l_cmd: f"{cmd} ", text)
            text = text.replace(g_char, l_cmd)
    for g_char, l_cmd in _GREEK_UPPER.items():
        if g_char in text:
            text = re.sub(rf"{re.escape(g_char)}(?=[a-zA-Z])", lambda m, cmd=l_cmd: f"{cmd} ", text)
            text = text.replace(g_char, l_cmd)
    return text


def convert_unicode_math_symbols(text: str) -> str:
    """Convert Unicode math operators and symbols to LaTeX."""
    if not text:
        return text

    # Handle square roots
    text = re.sub(r"√\(([^)]+)\)", r"\\sqrt{\1}", text)
    text = re.sub(r"√([a-zA-Z0-9]+)", r"\\sqrt{\1}", text)
    text = text.replace("√", r"\sqrt{}")

    # Replace operators
    for op, l_cmd in _MATH_OPERATORS.items():
        if op in text:
            text = text.replace(op, l_cmd)

    return text


def convert_vectors_and_hats(text: str) -> str:
    """Convert vector arrows and hats to LaTeX."""
    if not text:
        return text

    # Combining vector arrow \u20D7
    text = re.sub(r"([a-zA-Z])\u20D7", r"\\vec{\1}", text)

    # Unit vector hats
    text = text.replace("î", r"\hat{i}").replace("î", r"\hat{i}").replace("i\u0302", r"\hat{i}")
    text = text.replace("ĵ", r"\hat{j}").replace("j\u0302", r"\hat{j}")
    text = text.replace("k̂", r"\hat{k}").replace("k\u0302", r"\hat{k}")

    return text


def convert_scientific_notation(text: str) -> str:
    """Convert scientific notation expressions like 3.0 x 10^8 to LaTeX."""
    if not text:
        return text

    # First handle any remaining superscript forms in 10
    text = convert_unicode_super_sub(text)

    # Pattern: 3.0 x 10^8 or 3.0 \times 10^{8} or 3.0 * 10^8
    sci_re = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:[x×*]|\\times)\s*10(?:\^([+-]?\d+)|\^{([+-]?\d+)})"
    )

    def _repl_sci(m: re.Match) -> str:
        coef = m.group(1)
        exp = m.group(2) or m.group(3)
        return f"{coef} \\times 10^{{{exp}}}"

    return sci_re.sub(_repl_sci, text)


def convert_scientific_units(text: str) -> str:
    """Format scientific units after numbers."""
    if not text:
        return text

    common_units = {
        "m/s", "km/h", "m/s^2", "m s^{-1}", "m s^{-2}", "kg m s^{-2}",
        "kg/m^3", "N/m^2", "J/s", "W/m^2", "rad/s", "cm", "mm", "nm", "pm",
        "kg", "mg", "mol", "K", "eV", "MeV", "Hz", "kHz", "MHz", "GHz",
        "Pa", "kPa", "MPa", "atm", "bar", "J", "kJ", "W", "kW", "MW",
        "V", "mV", "kV", "A", "mA", "muA", "C", "muC", "F", "muF", "pF",
        "H", "mH", "muH", "T", "G", "Wb", "lm", "lx", "Bq", "Gy", "Sv",
    }

    # Match number followed by known unit (handle end of unit without word-boundary constraint on braces)
    for u in sorted(common_units, key=len, reverse=True):
        pattern = re.compile(rf"(\d+(?:\.\d+)?)\s+({re.escape(u)})(?![a-zA-Z0-9])")
        text = pattern.sub(rf"\1 \\text{{ \2}}", text)

    return text


def tokenize_and_convert_math(text: str) -> str:
    """Complete tokenizer and symbol conversion pipeline."""
    if not text:
        return text

    text = convert_unicode_fractions(text)
    text = convert_unicode_super_sub(text)
    text = convert_greek_letters(text)
    text = convert_unicode_math_symbols(text)
    text = convert_vectors_and_hats(text)
    text = convert_scientific_notation(text)
    text = convert_scientific_units(text)

    return text
