"""Tests for notation delimiter and LaTeX syntax validation."""

from __future__ import annotations

import pytest

from examforge.notation.validation import (
    validate_latex_syntax,
    validate_math_delimiters,
)


class TestDelimiterValidation:
    def test_balanced_single_dollars(self):
        is_ok, issues = validate_math_delimiters("Let $\\theta = 30^{\\circ}$ be the angle.")
        assert is_ok is True
        assert len(issues) == 0

    def test_unbalanced_dollars(self):
        is_ok, issues = validate_math_delimiters("Let $\\theta = 30^{\\circ} be the angle.")
        assert is_ok is False
        assert any("odd number of dollar delimiters" in iss.lower() for iss in issues)

    def test_balanced_double_dollars(self):
        is_ok, issues = validate_math_delimiters("$$x^{2} + y^{2} = r^{2}$$")
        assert is_ok is True


class TestLatexSyntaxValidation:
    def test_valid_commands_and_groups(self):
        is_ok, issues = validate_latex_syntax(r"\frac{1}{2} \sqrt{2gh} \Delta E")
        assert is_ok is True
        assert len(issues) == 0

    def test_unclosed_brace(self):
        is_ok, issues = validate_latex_syntax(r"\frac{1}{2")
        assert is_ok is False
        assert any("brace" in iss.lower() for iss in issues)

    def test_mismatched_closing_brace(self):
        is_ok, issues = validate_latex_syntax(r"x} + y")
        assert is_ok is False
        assert any("brace" in iss.lower() for iss in issues)
