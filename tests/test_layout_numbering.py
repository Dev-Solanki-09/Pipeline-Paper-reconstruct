"""Tests for numbering, option schemes, chemical formula guard, and monotonicity (Phase 6.4)."""

from __future__ import annotations

import random
import pytest

from examforge.layout.numbering import (
    NumberingEngine,
    ParsedQuestionStart,
    is_chemical_formula_or_prose_ref,
    is_valid_monotonic_step,
    parse_options_from_text,
)


class TestNumberingCorpus:
    @pytest.fixture
    def engine(self):
        return NumberingEngine(
            patterns=[
                r"^\s*(\d{1,3})\s*[.):]",
                r"^\s*Q\.?\s*(\d{1,3})\s*[.):]?",
                r"^\s*\((\d{1,3})\)\s*",
                r"^\s*प्र(?:श्न)?\.?\s*(\d{1,3})\s*[.):]?",
            ],
            sections=[r"SECTION\s+[A-Z]", r"PART\s+[0-9IVX]+"],
            label_schemes=["(1)", "(2)", "(3)", "(4)", "(A)", "(B)", "(C)", "(D)"],
        )

    def test_question_starts_positive_corpus(self, engine):
        positive_cases = [
            ("1. What is acceleration?", 1),
            ("2. Calculate kinetic energy.", 2),
            ("Q.26 Which of the following is true?", 26),
            ("Q27. The momentum is given by...", 27),
            ("(28) Find the derivative of f(x).", 28),
            ("29) What is the value of g?", 29),
            ("30: Solve the differential equation.", 30),
            ("प्र.31 निम्नलिखित में से कौन सा सही है?", 31),
            ("प्रश्न 32. ऊर्जा का मात्रक क्या है?", 32),
            ("100. Final question of section.", 100),
        ]
        for text, expected_num in positive_cases:
            match = engine.match_question_start(text)
            assert match is not None, f"Failed to match positive case: {text}"
            assert match.number == expected_num, f"Wrong number for {text}: got {match.number}, want {expected_num}"

    def test_chemical_formula_negative_guard(self):
        # Must NOT be detected as a question start
        chem_cases = [
            "2. SO3 is a planar molecule",
            "1. H2O has bent structure",
            "3. NH3 acts as a Lewis base",
            "4. CO2 is a linear gas",
            "2. Fe2O3 is ferric oxide",
            "1. NaCl crystallizes in FCC",
            "2. KMnO4 is a strong oxidizing agent",
            "3. Ca(OH)2 is slaked lime",
            "1. CH3COOH is a weak acid",
            "2. NO2 dimerizes to N2O4",
        ]
        for text in chem_cases:
            assert is_chemical_formula_or_prose_ref(text), f"Failed to guard chemical formula: {text}"

    def test_prose_reference_negative_guard(self):
        # Prose references must not be treated as question starts or options
        prose_cases = [
            "According to Statement (1), the velocity is constant.",
            "From Equation (2), we get x = 5.",
            "As shown in Figure (3), the magnetic field is directed inwards.",
            "In Step (4), the reagent is added slowly.",
            "Refer to Condition (1) above.",
            "Based on Reaction (2), delta H is negative.",
            "From Case (3), the pressure remains constant.",
            "As per Part (1) of the experiment.",
        ]
        for text in prose_cases:
            assert is_chemical_formula_or_prose_ref(text), f"Failed to guard prose reference: {text}"

    def test_numbering_corpus_200_cases(self, engine):
        """Generate a diverse 200-case corpus of questions, chemical formulas, options, and prose."""
        corpus = []
        # 100 valid question starts
        for i in range(1, 101):
            corpus.append((f"{i}. Problem statement {i} in mechanics.", True, i))

        # 50 chemical formulas (should not be question starts)
        formulas = ["SO3", "H2O", "NH3", "CO2", "CH4", "O2", "N2", "HCl", "NaOH", "H2SO4"]
        for i in range(1, 51):
            formula = formulas[i % len(formulas)]
            corpus.append((f"2. {formula} reaction coefficient.", False, None))

        # 50 prose references
        prose_types = ["Statement", "Equation", "Figure", "Condition", "Reaction"]
        for i in range(1, 51):
            ptype = prose_types[i % len(prose_types)]
            corpus.append((f"From {ptype} ({i % 4 + 1}), it follows that...", False, None))

        assert len(corpus) == 200

        for text, should_match, expected_num in corpus:
            match = engine.match_question_start(text)
            if should_match:
                assert match is not None, f"Expected match for: {text}"
                assert match.number == expected_num
            else:
                # If it matched regex, the guard must reject it
                if match is not None:
                    assert is_chemical_formula_or_prose_ref(text), f"Did not reject negative case: {text}"

    def test_monotonicity_guard(self):
        assert is_valid_monotonic_step(current_num=10, next_num=11, current_section="A", next_section="A")
        assert is_valid_monotonic_step(current_num=10, next_num=13, current_section="A", next_section="A") # small gap
        assert not is_valid_monotonic_step(current_num=10, next_num=2, current_section="A", next_section="A") # backward step
        # Reset allowed across sections
        assert is_valid_monotonic_step(current_num=30, next_num=1, current_section="PHYSICS", next_section="CHEMISTRY")

    def test_property_random_digits_never_produce_non_monotone_splits(self, engine):
        rng = random.Random(1337)
        words = ["alpha", "beta", "gamma", "energy", "force", "mass", "1.5", "3.14", "10^5", "SO2", "CO"]
        
        sequence: list[int] = []
        curr = None
        for _ in range(100):
            num = rng.randint(1, 150)
            text = f"{num}. " + " ".join(rng.choice(words) for _ in range(5))
            match = engine.match_question_start(text)
            if match and not is_chemical_formula_or_prose_ref(text):
                if curr is None or is_valid_monotonic_step(curr, match.number, "SEC", "SEC"):
                    sequence.append(match.number)
                    curr = match.number

        # Sequence must be monotonically non-decreasing
        for i in range(len(sequence) - 1):
            assert sequence[i] <= sequence[i + 1]

    def test_parse_options_schemes(self):
        text_num = "What is the force?\n(1) 10 N\n(2) 20 N\n(3) 30 N\n(4) 40 N"
        stem, opts = parse_options_from_text(text_num, schemes=["(1)", "(2)", "(3)", "(4)"])
        assert len(opts) == 4
        assert [o.label for o in opts] == ["1", "2", "3", "4"]
        assert opts[0].text == "10 N"

        text_alpha = "Select the correct option:\n(A) True\n(B) False"
        stem, opts = parse_options_from_text(text_alpha, schemes=["(A)", "(B)", "(C)", "(D)"])
        assert len(opts) == 2
        assert [o.label for o in opts] == ["A", "B"]
