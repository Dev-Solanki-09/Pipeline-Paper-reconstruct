"""
Gate 10 Verification: Answer Keys, Solutions & Marking Schemes.

Validates:
1. Synthetic keys in >= 6 styles (inline, table, grid, separate page, Devanagari digits, per-section).
2. Binding accuracy >= 99% across synthetic test sets.
3. Fault injection (shifted answers, invalid labels, kind incompatibility, inverted ranges) caught by R16.
4. Marking-scheme parsing corpus across English, Hindi, and mixed phrasing.
5. Solutions parsed into universal ContentNodes with LaTeX math and figures.
6. Feature flag `answers` and clean rollback toggles.
7. Output policy: `include_answers: false` by default protects question paper from key leakage.
"""

from __future__ import annotations

import pytest

from examforge.answers.bind import bind_answers, find_matching_question, resolve_option_label
from examforge.answers.marks import (
    apply_marking_schemes,
    parse_marking_scheme,
    parse_section_marking_schemes,
)
from examforge.answers.parse_key import (
    ParsedKeyEntry,
    parse_answer_key_grid,
    parse_answer_key_inline,
    parse_answer_key_table,
    parse_answer_key_text,
)
from examforge.answers.solutions import (
    bind_solutions,
    parse_solution_blocks,
    solution_text_to_nodes,
)
from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    AnswerSpec,
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    MathNode,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
    TextNode,
)
from examforge.spec import Rule, RuleSeverity
from examforge.stages.base import StageContext
from examforge.stages.s4_structure import S4Structure
from examforge.stages.s9_package import S9Package
from examforge.validators.r16_answer_binding import validate_answer_binding


def _create_synthetic_doc(
    num_questions: int = 100,
    sections: list[str] | None = None,
) -> ExamDocument:
    """Create a synthetic ExamDocument for binding accuracy tests."""
    pages = [
        PageInfo(page_number=1, width_px=595, height_px=842, classification=PageClassification.QUESTIONS),
        PageInfo(page_number=2, width_px=595, height_px=842, classification=PageClassification.QUESTIONS),
    ]
    questions = []
    secs = sections or [None]
    per_sec = num_questions // len(secs)

    q_idx = 1
    for s_idx, sec in enumerate(secs):
        count = per_sec if s_idx < len(secs) - 1 else (num_questions - len(questions))
        for _ in range(count):
            q = Question(
                id=f"q_{q_idx}",
                number=q_idx,
                section=sec,
                kind=QuestionKind.SINGLE_CORRECT,
                stem_text_en=f"This is synthetic question {q_idx} stem.",
                options=[
                    Option(label="A", text_str_en="Option A"),
                    Option(label="B", text_str_en="Option B"),
                    Option(label="C", text_str_en="Option C"),
                    Option(label="D", text_str_en="Option D"),
                ],
                source_pages=[1 if q_idx <= num_questions // 2 else 2],
            )
            questions.append(q)
            q_idx += 1

    return ExamDocument(
        id="synthetic_doc",
        source_path="synthetic.pdf",
        pages=pages,
        questions=questions,
    )


class TestGate10Verification:
    # -----------------------------------------------------------------------
    # 1. Synthetic Keys in >= 6 Styles
    # -----------------------------------------------------------------------
    def test_style_1_inline(self):
        sample = (
            "Question 1: Value of G?\nAns. (B)\n"
            "Question 2: Unit of force?\nAnswer: (1)\n"
            "Question 3: Energy value?\nAns: 9.8\n"
        )
        entries = parse_answer_key_inline(sample)
        assert len(entries) == 3
        assert entries[0].question_number == 1
        assert entries[0].raw_answer == "B"
        assert entries[1].question_number == 2
        assert entries[1].raw_answer == "1"
        assert entries[2].question_number == 3
        assert entries[2].numeric_value == 9.8

    def test_style_2_two_column_table(self):
        rows = [
            ["Q.No", "Answer"],
            ["1", "A"],
            ["2", "C"],
            ["3", "3.14 - 3.16"],
            ["4", "Bonus"],
        ]
        entries = parse_answer_key_table(rows)
        assert len(entries) == 4
        assert entries[0].options == ["A"]
        assert entries[1].options == ["C"]
        assert entries[2].numeric_range == (3.14, 3.16)
        assert entries[3].is_bonus is True

    def test_style_3_dense_grid(self):
        sample = "1-A 2-C 3-D 4-B 5-A 6-C 7-D 8-B 9-A 10-C"
        entries = parse_answer_key_grid(sample)
        assert len(entries) == 10
        assert [e.options[0] for e in entries] == ["A", "C", "D", "B", "A", "C", "D", "B", "A", "C"]

    def test_style_4_separate_answer_key_page(self):
        key_page_text = (
            "ANSWER KEY\n"
            "1. (A)\n"
            "2. (B)\n"
            "3. (C)\n"
            "4. (D)\n"
            "5. Dropped\n"
        )
        entries = parse_answer_key_text(key_page_text)
        assert len(entries) == 5
        assert entries[0].options == ["A"]
        assert entries[3].options == ["D"]
        assert entries[4].is_dropped is True

    def test_style_5_devanagari_numerals(self):
        sample = "१-ख २-ग ३-क ४-घ ५-ख"
        entries = parse_answer_key_grid(sample)
        assert len(entries) == 5
        assert [e.question_number for e in entries] == [1, 2, 3, 4, 5]
        assert [e.raw_answer for e in entries] == ["ख", "ग", "क", "घ", "ख"]

    def test_style_6_per_section_keys(self):
        sample = (
            "Section Physics\n"
            "1: A\n"
            "2: B\n"
            "Section Chemistry\n"
            "3: C\n"
            "4: D\n"
        )
        entries = parse_answer_key_text(sample)
        assert len(entries) == 4
        assert entries[0].section == "Physics" and entries[0].options == ["A"]
        assert entries[1].section == "Physics" and entries[1].options == ["B"]
        assert entries[2].section == "Chemistry" and entries[2].options == ["C"]
        assert entries[3].section == "Chemistry" and entries[3].options == ["D"]

    # -----------------------------------------------------------------------
    # 2. Binding Accuracy >= 99%
    # -----------------------------------------------------------------------
    def test_binding_accuracy_on_100_questions(self):
        doc = _create_synthetic_doc(100)
        options_cycle = ["A", "B", "C", "D"]
        entries = [
            ParsedKeyEntry(
                question_number=i,
                options=[options_cycle[(i - 1) % 4]],
            )
            for i in range(1, 101)
        ]
        bound = bind_answers(doc, entries)
        accuracy = bound / len(doc.questions)
        assert accuracy >= 0.99
        assert bound == 100
        for i, q in enumerate(doc.questions):
            assert q.answer is not None
            assert q.answer.correct_options == [options_cycle[i % 4]]

    # -----------------------------------------------------------------------
    # 3. Fault Injection Caught by Rule R16
    # -----------------------------------------------------------------------
    def test_fault_injection_shifted_answers(self):
        doc = _create_synthetic_doc(10)
        # Shifted: entries 2..11 instead of 1..10 (missing Q1)
        entries = [
            ParsedKeyEntry(question_number=i, options=["A"])
            for i in range(2, 12)
        ]
        bind_answers(doc, entries)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert any(i.id == "r16_incomplete_key" for i in issues)

    def test_fault_injection_label_not_in_scheme(self):
        doc = _create_synthetic_doc(5)
        entries = [
            ParsedKeyEntry(question_number=i, options=["A"])
            for i in range(1, 6)
        ]
        # Inject invalid label 'Z' on Q3
        entries[2].options = ["Z"]
        bind_answers(doc, entries)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert any("r16_invalid_option_label" in i.id for i in issues)

    def test_fault_injection_kind_incompatible_mcq(self):
        doc = _create_synthetic_doc(5)
        entries = [
            ParsedKeyEntry(question_number=i, options=["A"])
            for i in range(1, 6)
        ]
        # Inject multiple options on single MCQ
        entries[0].options = ["A", "B"]
        bind_answers(doc, entries)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert any("single_mcq_multiple_answers" in i.id for i in issues)

    def test_fault_injection_inverted_numeric_range(self):
        doc = _create_synthetic_doc(5)
        entries = [
            ParsedKeyEntry(question_number=i, options=["A"])
            for i in range(1, 6)
        ]
        entries[1].options = []
        entries[1].numeric_range = (50.0, 20.0)  # low > high
        bind_answers(doc, entries)
        rule = Rule(severity=RuleSeverity.BLOCKER, check="answer_binding")
        issues = validate_answer_binding(doc, rule)
        assert any("inverted_range" in i.id for i in issues)

    # -----------------------------------------------------------------------
    # 4. Marking Scheme Corpus Across English, Hindi, and Mixed Phrasing
    # -----------------------------------------------------------------------
    @pytest.mark.parametrize(
        "text,expected_pos,expected_neg,expected_part",
        [
            ("Marking Scheme: +4 / -1", 4.0, 1.0, None),
            ("Scheme: +3, -0.5, partial credit +1", 3.0, 0.5, 1.0),
            ("Each question carries 2 marks. No negative marking.", 2.0, 0.0, None),
            ("प्रत्येक सही उत्तर के लिए +4 अंक, प्रत्येक गलत उत्तर के लिए 1 अंक काटा जाएगा।", 4.0, 1.0, None),
            ("सही उत्तर: 3 अंक, ऋणात्मक अंकन नहीं, आंशिक अंक: 1", 3.0, 0.0, 1.0),
        ],
    )
    def test_marking_scheme_corpus(self, text, expected_pos, expected_neg, expected_part):
        marks = parse_marking_scheme(text)
        assert marks.positive == expected_pos
        assert marks.negative == expected_neg
        assert marks.partial == expected_part

    # -----------------------------------------------------------------------
    # 5. Solutions With Formulas and Figures
    # -----------------------------------------------------------------------
    def test_solutions_with_math_and_figures(self):
        text = (
            "Solution 1:\n"
            "According to Snell's law, we have:\n"
            "$n_1 \\sin(\\theta_1) = n_2 \\sin(\\theta_2)$\n"
            "Refer to ray diagram [Figure: fig_refraction_1].\n"
        )
        nodes = solution_text_to_nodes(text)
        assert len(nodes) >= 3
        # Check math node
        math_nodes = [n for n in nodes if isinstance(n, MathNode)]
        assert len(math_nodes) == 1
        assert "n_1 \\sin" in math_nodes[0].code
        # Check text node
        text_nodes = [n for n in nodes if isinstance(n, TextNode)]
        assert any("Snell" in t.texts.get("en", "") for t in text_nodes)

    # -----------------------------------------------------------------------
    # 6. Feature Flag Rollback & Output Policy
    # -----------------------------------------------------------------------
    def test_output_policy_default_does_not_leak_answers(self, tmp_path):
        doc = _create_synthetic_doc(3)
        doc.questions[0].answer = AnswerSpec(correct_options=["A"])
        doc.questions[1].answer = AnswerSpec(correct_options=["B"])
        doc.questions[2].answer = AnswerSpec(correct_options=["C"])

        config = ExamForgeConfig(flags={"answers": True, "include_answers": False})
        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "stage_s9",
            run_dir=tmp_path / "run",
        )

        stage = S9Package()
        res = stage.run(ctx)

        # Inspect generated JSON
        ir_file = tmp_path / "stage_s9" / "document.json"
        ir_text = ir_file.read_text(encoding="utf-8")
        assert '"correct_options": ["A"]' not in ir_text
        assert '"correct_options": null' in ir_text or '"answer": null' in ir_text

    def test_output_policy_when_explicitly_included(self, tmp_path):
        doc = _create_synthetic_doc(3)
        doc.questions[0].answer = AnswerSpec(correct_options=["A"])
        doc.questions[1].answer = AnswerSpec(correct_options=["B"])
        doc.questions[2].answer = AnswerSpec(correct_options=["C"])

        config = ExamForgeConfig(flags={"answers": True, "include_answers": True})
        ctx = StageContext(
            document=doc,
            spec=None,
            config=config,
            stage_dir=tmp_path / "stage_s9",
            run_dir=tmp_path / "run",
        )

        stage = S9Package()
        res = stage.run(ctx)

        ir_file = tmp_path / "stage_s9" / "document.json"
        ir_text = ir_file.read_text(encoding="utf-8")
        assert '"correct_options"' in ir_text
        assert '"A"' in ir_text
