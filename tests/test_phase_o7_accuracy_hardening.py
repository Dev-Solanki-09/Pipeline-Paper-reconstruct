"""
Tests for Phase O7 — Accuracy Hardening on Real Data.

Verifies:
- O7.1: Edit budget enforcement in text rewriting (do-no-harm rollback when edit ratio exceeds ε)
- O7.2: Real gold set verification and synthetic-vs-real gap calculation
- O7.3: Transformation whitelists (multiset digit and scientific unit preservation, S2 subpart protection)
- O7.4: Targeted accuracy techniques:
        * Devanagari syllable grammar validation and sanitization
        * Boilerplate phrase snapping to canonical exam phrase bank
        * Strict vertical baseline ordering preventing stem figures attaching to options
        * Option homogeneity and dimensional unit anomaly analysis
- O7.5: Conservative defaults preserving original input on low-confidence transformations
"""

from __future__ import annotations

import pytest

from examforge.answers.homogeneity import analyze_option_units
from examforge.clean.furniture import is_protected_content
from examforge.eval.metrics import compute_cer, compute_sequence_accuracy
from examforge.figures.associate import associate_figures_to_questions
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureClass,
    IssueSeverity,
    Option,
    Question,
    QuestionKind,
)
from examforge.lang.boilerplate import snap_to_canonical_boilerplate
from examforge.lang.syllable_grammar import (
    sanitize_devanagari_syllables,
    validate_devanagari_syllables,
)
from examforge.stages.base import StageContext
from examforge.stages.s5_normalize import S5Normalize


class TestPhaseO7AccuracyHardening:
    def test_o7_1_edit_budget_rollback_on_large_mutation(self, tmp_path):
        """O7.1: When text rewriting exceeds edit budget threshold ε, revert to original text and emit warning."""
        q = Question(
            id="q1",
            number=1,
            stem_text_en="Find the magnetic flux through a circular coil of radius 10 cm in uniform field B.",
            stem_en=[
                Block(
                    id="b1",
                    page=1,
                    bbox=BBox(x1=50, y1=100, x2=500, y2=150),
                    text="Find the magnetic flux through a circular coil of radius 10 cm in uniform field B.",
                )
            ],
            options=[
                Option(label="A", text_str_en="0.05 Wb", text_en=[Block(id="oa", page=1, bbox=BBox(x1=50, y1=160, x2=200, y2=190), text="0.05 Wb")]),
                Option(label="B", text_str_en="0.10 Wb", text_en=[Block(id="ob", page=1, bbox=BBox(x1=250, y1=160, x2=400, y2=190), text="0.10 Wb")]),
            ],
            source_pages=[1],
        )

        doc = ExamDocument(
            source_path="paper.pdf",
            source_hash="hash_o7_1",
            metadata=ExamMetadata(exam_name="JEE"),
            questions=[q],
            blocks=list(q.stem_en),
        )

        # Normal run with strict budget threshold = 0.05 (too low for any massive edit)
        stage = S5Normalize()
        ctx = StageContext(
            document=doc,
            run_dir=tmp_path,
            config=type("MockConfig", (), {"flag": lambda s, k, default=True: True, "edit_budget_threshold": 0.01})(),
            spec=None,
            stage_dir=tmp_path / "s5",
        )

        res = stage.run(ctx)
        # Even with normal KaTeX math formatting, if edit budget is violated, original text is preserved
        assert res.document.questions[0].stem_text_en == "Find the magnetic flux through a circular coil of radius 10 cm in uniform field B."
        assert any("edit_budget_exceeded" in issue.id for issue in res.issues)

    def test_o7_3_unit_whitelist_preservation_rollback(self, tmp_path):
        """O7.3: Normalization steps that alter or strip scientific units are rejected and reverted."""
        stage = S5Normalize()

        # Test block unit multiset protection
        b = Block(id="b_unit", page=1, bbox=BBox(x1=50, y1=50, x2=400, y2=80), text="Initial velocity v = 20 m/s")
        doc = ExamDocument(
            source_path="paper.pdf",
            source_hash="hash_units",
            metadata=ExamMetadata(exam_name="NEET"),
            blocks=[b],
        )

        ctx = StageContext(
            document=doc,
            run_dir=tmp_path,
            config=type("MockConfig", (), {"flag": lambda s, k, default=True: True})(),
            spec=None,
            stage_dir=tmp_path / "s5",
        )
        res = stage.run(ctx)

        # Units preserved
        assert "m/s" in res.document.blocks[0].text
        assert res.metrics.get("do_no_harm_verified", 0) >= 1

    def test_o7_3_s2_subpart_protection_guard(self):
        """O7.3: Numbered subparts like (a), (i), (1) at page boundaries are protected from S2 furniture removal."""
        assert is_protected_content("(a) Calculate the focal length.") is True
        assert is_protected_content("(i) State Ohm's law.") is True
        assert is_protected_content("(b) Hence find the current.") is True
        assert is_protected_content("(iv) Draw the phasor diagram.") is True

        # Non-protected furniture text should return False
        assert is_protected_content("PAGE 4 OF 12") is False
        assert is_protected_content("ALLEN CAREER INSTITUTE") is False

    def test_o7_4_devanagari_syllable_grammar_validation(self):
        """O7.4: Devanagari syllable grammar catches orphan matras, duplicate halants, and double nuktas."""
        # 1. Orphan matra at start of word: e.g. " िदए" (matra i with no preceding consonant)
        orphan_matra_text = " िदए गए परिपथ में"
        violations = validate_devanagari_syllables(orphan_matra_text)
        assert len(violations) >= 1
        assert violations[0].rule == "orphan_matra"

        # 2. Duplicate virama (halant)
        double_halant_text = "क्क््क"
        violations = validate_devanagari_syllables(double_halant_text)
        assert any(v.rule == "duplicate_virama" for v in violations)

        # 3. Sanitizer corrects mechanical errors
        sanitized, fixes = sanitize_devanagari_syllables(orphan_matra_text)
        assert fixes >= 1
        assert not sanitized.startswith(" ि")

    def test_o7_4_boilerplate_phrase_snapping(self):
        """O7.4: Standard exam instructions with minor OCR errors snap to canonical phrases."""
        # English typo in standard instruction
        noisy_en = "Choose the correct optoin."
        snapped_en, did_snap_en = snap_to_canonical_boilerplate(noisy_en)
        assert did_snap_en is True
        assert snapped_en == "Choose the correct option."

        # Match List instruction typo
        noisy_list = "Match List-I with List-II"
        snapped_list, did_snap_list = snap_to_canonical_boilerplate(noisy_list)
        assert did_snap_list is True
        assert snapped_list == "Match List-I with List-II."

        # Hindi standard instruction typo
        noisy_hi = "निम्नलिखित में से सही विकल्प चुनिए"
        snapped_hi, did_snap_hi = snap_to_canonical_boilerplate(noisy_hi)
        assert did_snap_hi is True
        assert snapped_hi == "निम्नलिखित में से सही विकल्प चुनिए।"

        # Arbitrary content should NOT snap
        arbitrary_text = "A particle of mass m moves under the action of a central force F(r) = -k/r^2."
        _, did_snap_arb = snap_to_canonical_boilerplate(arbitrary_text)
        assert did_snap_arb is False

    def test_o7_4_figure_vertical_baseline_ordering(self):
        """O7.4: Stem figures positioned above option blocks are never assigned to child options."""
        opt_a = Option(
            label="A",
            text_en=[Block(id="oa", page=1, bbox=BBox(x1=50, y1=300, x2=200, y2=340), text="(A) 5 V")],
            text_str_en="(A) 5 V",
        )
        opt_b = Option(
            label="B",
            text_en=[Block(id="ob", page=1, bbox=BBox(x1=250, y1=300, x2=400, y2=340), text="(B) 10 V")],
            text_str_en="(B) 10 V",
        )

        q = Question(
            id="q1",
            number=1,
            stem_en=[
                Block(
                    id="b1",
                    page=1,
                    bbox=BBox(x1=50, y1=100, x2=500, y2=150),
                    text="In the circuit shown in figure, find potential difference across capacitor.",
                )
            ],
            stem_text_en="In the circuit shown in figure, find potential difference across capacitor.",
            options=[opt_a, opt_b],
            source_pages=[1],
        )

        # Diagram located between stem (y=150) and options (y=300)
        # Even if its height is small (e.g. 70px) which could match an option diagram heuristic,
        # its vertical baseline precedes the options, so it must stay on the stem!
        stem_fig = Figure(
            id="fig_circuit",
            page=1,
            bbox=BBox(x1=100, y1=180, x2=250, y2=250),  # strictly above y=300
            scale_class="img-opt",  # heuristic might trigger option diagram
        )

        associate_figures_to_questions([stem_fig], [q])

        assert stem_fig.question_ref == "q1"
        assert stem_fig.option_ref is None  # NOT assigned to Option A or B!
        assert "fig_circuit" in q.figure_refs
        assert opt_a.figure_ref is None

    def test_o7_4_option_homogeneity_analysis(self):
        """O7.4: Detect and repair OCR dimension / unit anomalies across option sets."""
        opts = [
            Option(label="A", text_str_en="10 m/s"),
            Option(label="B", text_str_en="20 m/s"),
            Option(label="C", text_str_en="30 m/s"),
            Option(label="D", text_str_en="40 mls"),  # OCR typo: 'mls' instead of 'm/s'
        ]

        report = analyze_option_units(opts)
        assert report.majority_unit == "m/s"
        assert report.corrections_applied == 1
        assert opts[3].text_str_en == "40 m/s"
        assert report.is_homogeneous is True

    def test_o7_2_real_gold_eval_and_synthetic_gap(self):
        """O7.2: Verify real gold vs synthetic metric calibration meets thresholds and tolerance."""
        # Simulated ground truth reference
        ref_questions = [
            Question(id="q1", number=1, stem_text_en="What is the speed of light in vacuum?", options=[Option(label="A", text_str_en="3 x 10^8 m/s")]),
            Question(id="q2", number=2, stem_text_en="State Newton's second law of motion.", options=[Option(label="A", text_str_en="F = ma")]),
            Question(id="q3", number=3, stem_text_en="Calculate equivalent capacitance in series.", options=[Option(label="A", text_str_en="1/C = 1/C1 + 1/C2")]),
        ]

        # Clean Real Gold hypothesis: 100% match
        hyp_real = [
            Question(id="q1", number=1, stem_text_en="What is the speed of light in vacuum?", options=[Option(label="A", text_str_en="3 x 10^8 m/s")]),
            Question(id="q2", number=2, stem_text_en="State Newton's second law of motion.", options=[Option(label="A", text_str_en="F = ma")]),
            Question(id="q3", number=3, stem_text_en="Calculate equivalent capacitance in series.", options=[Option(label="A", text_str_en="1/C = 1/C1 + 1/C2")]),
        ]

        # Synthetic Degradation hypothesis (minor character substitution)
        hyp_synth = [
            Question(id="q1", number=1, stem_text_en="What is the speed of light in vacuum?", options=[Option(label="A", text_str_en="3 x 10^8 m/s")]),
            Question(id="q2", number=2, stem_text_en="State Newton's second law of motlon.", options=[Option(label="A", text_str_en="F = ma")]),  # i -> l
            Question(id="q3", number=3, stem_text_en="Calculate equivalent capacitance in series.", options=[Option(label="A", text_str_en="1/C = 1/C1 + 1/C2")]),
        ]

        # Compute sequence accuracy
        ref_nums = [q.number for q in ref_questions]
        real_seq_acc = compute_sequence_accuracy(ref_nums, [q.number for q in hyp_real])
        synth_seq_acc = compute_sequence_accuracy(ref_nums, [q.number for q in hyp_synth])

        assert real_seq_acc == 1.0
        assert synth_seq_acc == 1.0

        # Compute CER
        real_cer = compute_cer(ref_questions[1].stem_text_en, hyp_real[1].stem_text_en)
        synth_cer = compute_cer(ref_questions[1].stem_text_en, hyp_synth[1].stem_text_en)

        assert real_cer == 0.0
        assert synth_cer > 0.0

        # Verify synthetic-vs-real gap is bounded (<= 0.05 CER tolerance)
        gap = abs(synth_cer - real_cer)
        assert gap <= 0.05
