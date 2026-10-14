"""Tests for chemical formula parsing, KaTeX/mhchem formatting, and reaction balancing."""

from __future__ import annotations

import pytest

from examforge.notation.chemistry import (
    format_chemical_formula,
    format_chemical_reaction,
    is_chemical_equation,
    is_chemical_formula,
    parse_chemical_formula,
    validate_chemical_equation,
)


class TestChemicalFormula:
    def test_is_chemical_formula(self):
        assert is_chemical_formula("H2SO4") is True
        assert is_chemical_formula("KMnO4") is True
        assert is_chemical_formula("Ca(OH)2") is True
        assert is_chemical_formula("Fe3+") is True
        assert is_chemical_formula("SO4^2-") is True
        assert is_chemical_formula("Calculate the work") is False
        assert is_chemical_formula("velocity") is False

    def test_parse_atoms_count(self):
        atoms, charge = parse_chemical_formula("H2SO4")
        assert atoms == {"H": 2, "S": 1, "O": 4}
        assert charge == 0

        atoms, charge = parse_chemical_formula("Ca(OH)2")
        assert atoms == {"Ca": 1, "O": 2, "H": 2}
        assert charge == 0

        atoms, charge = parse_chemical_formula("Fe^{3+}")
        assert atoms == {"Fe": 1}
        assert charge == 3

        atoms, charge = parse_chemical_formula("SO4^{2-}")
        assert atoms == {"S": 1, "O": 4}
        assert charge == -2

    def test_format_chemical_formula(self):
        # Without mhchem
        plain = format_chemical_formula("H2SO4", use_mhchem=False)
        assert plain == r"\text{H}_{2}\text{SO}_{4}"

        # With mhchem
        mhchem = format_chemical_formula("H2SO4", use_mhchem=True)
        assert mhchem == r"\ce{H2SO4}"

    def test_state_symbols(self):
        plain = format_chemical_formula("NaCl(aq)", use_mhchem=False)
        assert plain == r"\text{NaCl}\text{(aq)}"

    def test_oxidation_states(self):
        plain = format_chemical_formula("Fe(III)", use_mhchem=False)
        assert plain == r"\text{Fe(III)}"


class TestChemicalReaction:
    def test_is_chemical_equation(self):
        assert is_chemical_equation("2H2 + O2 -> 2H2O") is True
        assert is_chemical_equation("N2 + 3H2 <=> 2NH3") is True
        assert is_chemical_equation("x + y = z") is False

    def test_reaction_arrows_formatting(self):
        eq = "2H2 + O2 -> 2H2O"
        formatted = format_chemical_reaction(eq, use_mhchem=False)
        assert r"\rightarrow" in formatted

    def test_validate_balanced_equation(self):
        balanced = "2H2 + O2 -> 2H2O"
        is_ok, issues = validate_chemical_equation(balanced)
        assert is_ok is True
        assert len(issues) == 0

    def test_validate_unbalanced_equation(self):
        unbalanced = "H2 + O2 -> H2O"
        is_ok, issues = validate_chemical_equation(unbalanced)
        assert is_ok is False
        assert any("atom balance" in iss.lower() for iss in issues)

    def test_validate_charge_balance(self):
        # 2Fe^{3+} + Sn^{2+} -> 2Fe^{2+} + Sn^{4+} (balanced: charge 6+ -> 6+)
        balanced = "2Fe^{3+} + Sn^{2+} -> 2Fe^{2+} + Sn^{4+}"
        is_ok, issues = validate_chemical_equation(balanced)
        assert is_ok is True

        # Unbalanced charge
        unbalanced_charge = "Fe^{3+} + Sn^{2+} -> Fe^{2+} + Sn^{4+}"
        is_ok, issues = validate_chemical_equation(unbalanced_charge)
        assert is_ok is False
        assert any("charge balance" in iss.lower() for iss in issues)
