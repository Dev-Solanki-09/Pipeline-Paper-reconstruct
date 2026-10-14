"""Tests for notation tokenizer: Unicode to LaTeX, Greek, operators, units, vectors."""

from __future__ import annotations

import pytest

from examforge.notation.canonical import (
    canonicalize_number,
    canonicalize_unit,
    canonicalize_value_with_unit,
)
from examforge.notation.tokenizer import (
    convert_greek_letters,
    convert_scientific_notation,
    convert_scientific_units,
    convert_unicode_fractions,
    convert_unicode_math_symbols,
    convert_unicode_super_sub,
    convert_vectors_and_hats,
    tokenize_and_convert_math,
)


class TestUnicodeConversion:
    def test_superscripts_and_subscripts(self):
        assert convert_unicode_super_sub("x² + y³ = z⁴") == "x^{2} + y^{3} = z^{4}"
        assert convert_unicode_super_sub("a₀ + a₁x + a₂x²") == "a_{0} + a_{1}x + a_{2}x^{2}"
        assert convert_unicode_super_sub("10⁻⁵") == "10^{-5}"

    def test_adjacent_scripts_combined(self):
        assert convert_unicode_super_sub("x²³") == "x^{23}"
        assert convert_unicode_super_sub("a₁₂") == "a_{12}"

    def test_fractions(self):
        assert convert_unicode_fractions("½ mv²") == r"\frac{1}{2} mv²"
        assert convert_unicode_fractions("¾ R") == r"\frac{3}{4} R"

    def test_greek_letters(self):
        assert convert_greek_letters("α, β, γ, θ, λ, μ, π, ω") == (
            r"\alpha, \beta, \gamma, \theta, \lambda, \mu, \pi, \omega"
        )
        assert convert_greek_letters("ΔE = hν") == r"\Delta E = h\nu"
        assert convert_greek_letters("Ω") == r"\Omega"

    def test_math_operators(self):
        assert convert_unicode_math_symbols("a × b ≤ c ÷ d") == r"a \times b \le c \div d"
        assert convert_unicode_math_symbols("x ± y ≈ z") == r"x \pm y \approx z"
        assert convert_unicode_math_symbols("A ∪ B ∩ C") == r"A \cup B \cap C"
        assert convert_unicode_math_symbols("30°") == r"30^{\circ}"

    def test_vectors_and_hats(self):
        # Combining vector arrow \u20D7
        assert convert_vectors_and_hats("v\u20D7") == r"\vec{v}"
        assert convert_vectors_and_hats("F\u20D7") == r"\vec{F}"
        # Unit hats
        assert convert_vectors_and_hats("î + 2ĵ - 3k̂") == r"\hat{i} + 2\hat{j} - 3\hat{k}"

    def test_scientific_notation(self):
        assert convert_scientific_notation("3.0 x 10^8") == r"3.0 \times 10^{8}"
        assert convert_scientific_notation("6.626 × 10⁻³⁴") == r"6.626 \times 10^{-34}"

    def test_scientific_units(self):
        assert convert_scientific_units("10 m/s") == r"10 \text{ m/s}"
        assert convert_scientific_units("5.0 kg m s^{-2}") == r"5.0 \text{ kg m s^{-2}}"

    def test_full_pipeline_tokenization(self):
        raw = "Calculate kinetic energy K = ½mv² where m = 2 kg and v = 10 m/s."
        converted = tokenize_and_convert_math(raw)
        assert r"\frac{1}{2}" in converted
        assert "^{2}" in converted


class TestCanonicalization:
    def test_number_canonicalization(self):
        assert canonicalize_number("3.140") == "3.14"
        assert canonicalize_number("10,000") == "10000"
        assert canonicalize_number("05") == "5"
        assert canonicalize_number("-0.50") == "-0.5"

    def test_unit_canonicalization(self):
        assert canonicalize_unit("m/s") == "m s^{-1}"
        assert canonicalize_unit("km/h") == "km h^{-1}"
        assert canonicalize_unit("N/m^2") == "N m^{-2}"

    def test_value_with_unit(self):
        val, unit = canonicalize_value_with_unit("10.0 m/s")
        assert val == "10"
        assert unit == "m s^{-1}"
