"""Tests for math delimiter wrapping and negative prose preservation."""

from __future__ import annotations

import pytest

from examforge.notation.wrapping import wrap_math_delimiters


class TestMathWrapping:
    def test_pure_formula_wrapped(self):
        res = wrap_math_delimiters(r"\theta = 30^{\circ}")
        assert res == r"$\theta = 30^{\circ}$"

    def test_inline_formula_in_prose(self):
        text = r"Given that \theta = 30^{\circ}, find the angle."
        res = wrap_math_delimiters(text)
        assert res == r"Given that $\theta = 30^{\circ}$, find the angle."

    def test_negative_prose_cases_never_wrapped(self):
        # Isolated single letters and numbers in English prose must NOT be wrapped in $...$
        prose1 = "A particle moves a distance x in meters."
        assert wrap_math_delimiters(prose1) == prose1

        prose2 = "Here m is the mass and v is the velocity."
        assert wrap_math_delimiters(prose2) == prose2

        prose3 = "There are 2 questions in section B."
        assert wrap_math_delimiters(prose3) == prose3

        prose4 = "Find the value of x if the car travels 100 meters."
        assert wrap_math_delimiters(prose4) == prose4

    def test_already_wrapped_not_doubled(self):
        wrapped = r"$\theta = 30^{\circ}$"
        assert wrap_math_delimiters(wrapped) == wrapped

        mixed = r"Angle is $\theta = 30^{\circ}$ and radius is $r = 5$."
        assert wrap_math_delimiters(mixed) == mixed

    def test_idempotence(self):
        samples = [
            r"Calculate kinetic energy E = \frac{1}{2}mv^{2} of the particle.",
            r"where \lambda = 500 nm is the wavelength.",
            r"Pure text without any formulas or commands.",
            r"$x^{2} + y^{2} = r^{2}$",
        ]
        for s in samples:
            once = wrap_math_delimiters(s)
            twice = wrap_math_delimiters(once)
            assert twice == once, f"Failed idempotence on: {s}"
