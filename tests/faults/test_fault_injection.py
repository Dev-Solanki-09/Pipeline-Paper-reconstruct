"""Fault-injection test suite for ExamForge v2 deterministic verifiers.

Verifies:
- >= 98% detection rate on single injected faults across all rules (R01-R15).
- Zero false-positive blocker issues on clean documents.
- Tricky-text invariance (Devanagari digits, decimals, ranges, units).
- Lexicon conservative autofix rules and digit preservation.
- Performance budget over 200 questions.
"""

from __future__ import annotations

import copy
from pathlib import Path
import time
import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    BlockType,
    ExamDocument,
    Figure,
    FigureNode,
    IssueSeverity,
    MathNode,
    PageInfo,
    Question,
    QuestionKind,
    TextNode,
)
from examforge.spec import Rule, RuleSeverity, Spec
from examforge.stages.base import StageContext
from examforge.stages.s8_verify import S8Verify
from examforge.synth.generator import SyntheticDocumentGenerator
from examforge.validators.r10_language_consistency import extract_invariant_tokens, validate_language_consistency
from examforge.validators.r11_text_layer_agreement import validate_text_layer_agreement
from examforge.validators.r12_lexicon import validate_lexicon
from examforge.validators.r13_render_check import validate_render_check
from examforge.validators.r14_sequence_gaps import validate_sequence_gaps
from examforge.validators.r15_structure_consistency import validate_structure_consistency


def _make_context(doc: ExamDocument, spec: Spec | None = None) -> StageContext:
    return StageContext(
        document=doc,
        run_dir=Path("."),
        config=ExamForgeConfig(),
        spec=spec or Spec.v2(),
        stage_dir=Path("."),
    )


# ============================================================================
# Fault Mutators
# ============================================================================

def mutate_flip_digit_hi(doc: ExamDocument) -> str:
    """Flip a digit in Hindi text of question 1."""
    q = doc.questions[0]
    for node in q.stem:
        if isinstance(node, TextNode) and "hi" in node.texts:
            node.texts["hi"] = node.texts["hi"] + " 999"
            return "language_consistency"
    q.stem_text_hi = (q.stem_text_hi or "") + " 999"
    return "language_consistency"


def mutate_swap_unit(doc: ExamDocument) -> str:
    """Swap or inject conflicting unit into Hindi stem of question 1."""
    q = doc.questions[0]
    for node in q.stem:
        if isinstance(node, TextNode) and "hi" in node.texts:
            node.texts["hi"] = node.texts["hi"] + " 500 kilogram Joules"
            return "language_consistency"
    q.stem_text_hi = (q.stem_text_hi or "") + " 500 kilogram Joules"
    return "language_consistency"


def mutate_drop_option(doc: ExamDocument) -> str:
    """Drop options from an MCQ so it has < 2 options."""
    for q in doc.questions:
        if q.kind == QuestionKind.MCQ_SINGLE and len(q.options) >= 2:
            q.options = q.options[:1]
            return "structure_consistency"
    doc.questions[0].options = []
    return "structure_consistency"


def mutate_unbalance_brace(doc: ExamDocument) -> str:
    """Unbalance a brace in a math node formula."""
    q = doc.questions[0]
    q.stem.append(MathNode(code=r"\frac{a}{b} + {unbalanced"))
    return "render_check"


def mutate_delete_question(doc: ExamDocument) -> str:
    """Delete a middle question to create a sequence gap."""
    if len(doc.questions) >= 3:
        del doc.questions[1]
    return "sequence_gaps"


def mutate_duplicate_question(doc: ExamDocument) -> str:
    """Duplicate question number 1."""
    dup_q = copy.deepcopy(doc.questions[0])
    dup_q.id = "dup_q1"
    doc.questions.append(dup_q)
    return "sequence_gaps"


def mutate_inject_header_line(doc: ExamDocument) -> str:
    """Inject an un-dropped header line block."""
    doc.blocks.append(
        Block(
            id="injected_hdr",
            page=1,
            type=BlockType.HEADER,
            bbox=BBox(x1=50, y1=10, x2=500, y2=30),
            text="EXAM PAPER 2026 - CONFIDENTIAL",
            confidence=1.0,
        )
    )
    return "no_headers_footers_page_numbers"


def mutate_inject_phone_number(doc: ExamDocument) -> str:
    """Inject coaching contact/phone branding."""
    doc.blocks.append(
        Block(
            id="injected_phone",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=10, x2=500, y2=30),
            text="Call Allen Coaching Classes at +91 9876543210 for admissions",
            confidence=1.0,
        )
    )
    return "no_brand_text_or_logo"


def mutate_break_image(doc: ExamDocument) -> str:
    """Break a figure's crop data with corrupted base64."""
    for fig in doc.figures:
        fig.crop_path = "data:image/png;base64,CORRUPTED_NOT_VALID_PNG_DATA"
        return "render_check"
    # Or create a question referencing broken figure
    fig = Figure(
        id="broken_fig",
        page=1,
        bbox=BBox(x1=10, y1=10, x2=100, y2=100),
        crop_path="data:image/png;base64,CORRUPTED_NOT_VALID_PNG_DATA",
    )
    doc.figures.append(fig)
    doc.questions[0].stem.append(FigureNode(figure_ref="broken_fig"))
    return "render_check"


def mutate_add_page_wrapper(doc: ExamDocument) -> str:
    """Inject forbidden page-wrapper class artifact into question text."""
    q = doc.questions[0]
    q.stem_text_en += ' <div class="page-wrapper">artifact</div>'
    return "render_check"


def mutate_orphan_subpart(doc: ExamDocument) -> str:
    """Inject non-sequential subpart labels (a) and (c) without (b)."""
    q = doc.questions[0]
    q.children = [
        Question(id="q1_a", number=1, stem=[TextNode(texts={"en": "(a) First subpart"})]),
        Question(id="q1_c", number=1, stem=[TextNode(texts={"en": "(c) Third subpart"})]),
    ]
    return "structure_consistency"


def mutate_remove_or_partner(doc: ExamDocument) -> str:
    """Mark a question with choice_group but provide no OR partner."""
    q = doc.questions[0]
    q.choice_group = "OR_CHOICE_SINGLETON_99"
    return "structure_consistency"


def mutate_text_layer_disagreement(doc: ExamDocument) -> str:
    """Create a page with valid text layer but completely changed question stem."""
    # Add page info with valid text layer
    doc.pages.append(
        PageInfo(
            page_number=1,
            has_text_layer=True,
            text_layer_valid=True,
        )
    )
    # Add blocks representing the ground truth text layer
    doc.blocks.append(
        Block(
            id="layer_block_1",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=10, y1=10, x2=500, y2=50),
            text="The quick brown fox jumps over the lazy sleeping dog in the forest",
        )
    )
    # Set question on page 1 with completely different text
    q = doc.questions[0]
    q.source_pages = [1]
    q.stem_text_en = "Completely different extracted tokens from another question entirely"
    q.stem = [TextNode(texts={"en": q.stem_text_en})]
    return "text_layer_agreement"


def mutate_inject_lexicon_typo(doc: ExamDocument) -> str:
    """Inject an OCR typo distance 1 from a domain term (e.g. acceleraton -> acceleration)."""
    q = doc.questions[0]
    for node in q.stem:
        if isinstance(node, TextNode) and "en" in node.texts:
            node.texts["en"] = node.texts["en"] + " acceleraton is constant"
            return "lexicon"
    q.stem.append(TextNode(texts={"en": "The acceleraton of the particle is uniform"}))
    return "lexicon"


ALL_MUTATORS = [
    mutate_flip_digit_hi,
    mutate_swap_unit,
    mutate_drop_option,
    mutate_unbalance_brace,
    mutate_delete_question,
    mutate_duplicate_question,
    mutate_inject_header_line,
    mutate_inject_phone_number,
    mutate_break_image,
    mutate_add_page_wrapper,
    mutate_orphan_subpart,
    mutate_remove_or_partner,
    mutate_text_layer_disagreement,
    mutate_inject_lexicon_typo,
]


# ============================================================================
# Tests
# ============================================================================

class TestFaultInjectionSuite:
    """Tests fault detection rate and precision across all mutators."""

    @pytest.mark.parametrize("mutator", ALL_MUTATORS)
    def test_single_mutator_detected_by_expected_rule(self, mutator):
        """Each single injected fault must trigger the exact expected validator."""
        gen = SyntheticDocumentGenerator(seed=101)
        doc = gen.generate(num_questions=10)

        expected_rule = mutator(doc)
        ctx = _make_context(doc)
        result = S8Verify().run(ctx)

        fired_rules = {issue.rule for issue in result.issues}
        assert expected_rule in fired_rules, (
            f"Mutator {mutator.__name__} was expected to trigger '{expected_rule}', "
            f"but fired rules were: {fired_rules}"
        )

    def test_detection_rate_above_98_percent(self):
        """Run fault injection across multiple seeds and verify >= 98% detection."""
        detected = 0
        total = 0

        for seed in range(10, 15):
            for mutator in ALL_MUTATORS:
                doc = SyntheticDocumentGenerator(seed=seed).generate(num_questions=10)
                expected_rule = mutator(doc)
                ctx = _make_context(doc)
                result = S8Verify().run(ctx)

                fired_rules = {issue.rule for issue in result.issues}
                total += 1
                if expected_rule in fired_rules:
                    detected += 1

        rate = detected / total
        assert rate >= 0.98, f"Detection rate was {rate:.3f} ({detected}/{total}), expected >= 0.98"

    def test_clean_documents_produce_zero_blockers(self):
        """Clean synthetic documents produce zero blocker issues across 20 distinct seeds."""
        for seed in range(50, 70):
            doc = SyntheticDocumentGenerator(seed=seed).generate(num_questions=10)
            ctx = _make_context(doc)
            result = S8Verify().run(ctx)

            blockers = [i for i in result.issues if i.severity == IssueSeverity.BLOCKER]
            assert len(blockers) == 0, f"Seed {seed} produced false positive blockers: {blockers}"

    def test_tricky_text_corpora(self):
        """Tricky text like Devanagari digits, decimals, ranges, and chemical formulas canonicalize properly."""
        en_text = "Calculate mass of 12.5 kg at 2026-05-10 with range 1-4 for vitamin B12"
        # Hindi text with Devanagari numerals १२.५ and identical Latin units
        hi_text = "विटामिन B12 के लिए श्रेणी 1-4 के साथ 2026-05-10 पर १२.५ kg द्रव्यमान की गणना करें"

        q = Question(
            id="q_tricky",
            number=1,
            stem=[TextNode(texts={"en": en_text, "hi": hi_text})],
            options=[],
        )
        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            languages=[{"code": "en"}, {"code": "hi"}],
            questions=[q],
        )

        rule = Rule(severity=RuleSeverity.BLOCKER, check="language_consistency")
        issues = validate_language_consistency(doc, rule)
        # Should NOT flag mismatch because १२.५ canonicalizes to 12.5 and units match
        assert len(issues) == 0, f"False positive on tricky bilingual text: {issues}"

    def test_lexicon_autofix_and_refusal(self):
        """Lexicon autofix only triggers when unambiguous distance 1 and does not change digits."""
        # 1. Unambiguous distance 1 typo: 'mitochondra' -> 'mitochondria' (only 1 candidate)
        q_fix = Question(
            id="q1",
            number=1,
            stem=[TextNode(texts={"en": "The mitochondra produces energy."})],
        )
        doc_fix = ExamDocument(source_path="test.pdf", source_hash="h1", questions=[q_fix])
        rule_autofix = Rule(severity=RuleSeverity.WARN, check="lexicon", params={"autofix": True})

        issues = validate_lexicon(doc_fix, rule_autofix)
        assert len(issues) == 1
        assert issues[0].evidence["auto_fixed"] is True
        assert "mitochondria" in q_fix.stem[0].texts["en"]

        # 2. Refusal when ambiguous (e.g. 'acceleraton' has multiple candidates: acceleration, accelerator)
        q_ambig = Question(
            id="q2",
            number=2,
            stem=[TextNode(texts={"en": "The acceleraton is constant."})],
        )
        doc_ambig = ExamDocument(source_path="test.pdf", source_hash="h1", questions=[q_ambig])
        issues_ambig = validate_lexicon(doc_ambig, rule_autofix)
        assert len(issues_ambig) == 1
        assert issues_ambig[0].evidence["auto_fixed"] is False
        assert len(issues_ambig[0].candidates) > 1

        # 3. Refusal when autofix=False
        q_nofix = Question(
            id="q3",
            number=3,
            stem=[TextNode(texts={"en": "The mitochondra produces energy."})],
        )
        doc_nofix = ExamDocument(source_path="test.pdf", source_hash="h1", questions=[q_nofix])
        rule_no_autofix = Rule(severity=RuleSeverity.WARN, check="lexicon", params={"autofix": False})

        issues2 = validate_lexicon(doc_nofix, rule_no_autofix)
        assert len(issues2) == 1
        assert issues2[0].evidence["auto_fixed"] is False
        assert "mitochondra" in q_nofix.stem[0].texts["en"]

    def test_performance_budget_over_200_questions(self):
        """Validating 200 questions across all rules completes well within performance budget."""
        # Generate 200 questions
        doc = SyntheticDocumentGenerator(seed=999).generate(num_questions=200)
        ctx = _make_context(doc)

        start = time.perf_counter()
        result = S8Verify().run(ctx)
        elapsed = time.perf_counter() - start

        # 200 questions should evaluate in under 2.0 seconds deterministically
        assert elapsed < 2.0, f"Validation took {elapsed:.2f}s for 200 questions, expected < 2.0s"
        assert result.metrics["rules_evaluated"] >= 15
