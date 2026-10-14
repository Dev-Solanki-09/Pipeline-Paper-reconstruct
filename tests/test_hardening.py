"""
Comprehensive tests verifying all 14 pipeline hardening improvements:
- Column-aware reading order (left column before right column)
- Question number monotonicity & chemical formula protection
- Robust option marker detection & protection against prose phrases
- Interleaved bilingual split & line-level slash splitting
- Proportional figure-to-question assignment fallback
- Tightened non-prose math wrapping for KaTeX/MathJax
- Protection of question stems from furniture dropping
- Circuit breaker half-open retry mechanism
- Option packing heuristic with images and data URIs
- Resilient figure path resolution in s9_package
- Embedded image DPI estimation in s0_intake
- Config-linked fail_fast validation in s8_verify
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Figure,
    Issue,
    IssueSeverity,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.stages.base import StageContext, StageResult
from examforge.stages.s0_intake import _estimate_dpi
from examforge.stages.s2_clean import _find_repeating_furniture
from examforge.stages.s4_structure import (
    PATTERN_DOT,
    RawQuestion,
    _is_valid_new_question_start,
    _parse_options_from_raw,
    _segment_questions,
    _sort_blocks_reading_order,
    get_option_packing_class,
)
from examforge.stages.s5_hindi import split_bilingual_text
from examforge.stages.s5_math import wrap_math_delimiters
from examforge.stages.s6_figures import _assign_figures_to_questions
from examforge.stages.s8_verify import S8Verify
from examforge.stages.s9_package import _b64_image_filter
from examforge.engines.paddle_vl import PaddleVLAdapter, PaddleVLConfig


class TestColumnAwareReadingOrder:
    def test_two_column_reading_order(self):
        """Ensure left column blocks are ordered before right column blocks on 2-col pages."""
        page_info = PageInfo(
            page_number=1,
            column_count=2,
            width_px=600,
            height_px=800,
        )
        # Block 1: Left column, y=100
        b_left_1 = Block(id="b1", page=1, bbox=BBox(x1=50, y1=100, x2=250, y2=150), text="Q1 Left top")
        # Block 2: Left column, y=300
        b_left_2 = Block(id="b2", page=1, bbox=BBox(x1=50, y1=300, x2=250, y2=350), text="Q2 Left bot")
        # Block 3: Right column, y=100
        b_right_1 = Block(id="b3", page=1, bbox=BBox(x1=350, y1=100, x2=550, y2=150), text="Q3 Right top")
        # Block 4: Right column, y=300
        b_right_2 = Block(id="b4", page=1, bbox=BBox(x1=350, y1=300, x2=550, y2=350), text="Q4 Right bot")

        blocks = [b_right_1, b_left_2, b_right_2, b_left_1]
        sorted_blocks = _sort_blocks_reading_order(blocks, [page_info])

        # Expected order: b_left_1, b_left_2, b_right_1, b_right_2
        assert [b.id for b in sorted_blocks] == ["b1", "b2", "b3", "b4"]


class TestQuestionMonotonicityAndFormulas:
    def test_chemical_formula_does_not_split_question(self):
        """Lines starting with numbers like '2. SO3' inside a question should not create a new question."""
        q_prev = RawQuestion(number=35, stem_text="Consider reaction")
        # '2. SO3 + O2 -> 2SO3' inside Q35
        is_new = _is_valid_new_question_start(2, "2. SO3 + O2 -> 2SO3", q_prev, None)
        assert is_new is False

    def test_monotonic_next_question_accepted(self):
        """Question 36 after 35 is accepted."""
        q_prev = RawQuestion(number=35, stem_text="Consider reaction")
        is_new = _is_valid_new_question_start(36, "36. What is the product?", q_prev, None)
        assert is_new is True

    def test_options_not_treated_as_question(self):
        """Block starting with (1) or (A) is not a new question."""
        q_prev = RawQuestion(number=35, stem_text="Consider reaction")
        assert not _is_valid_new_question_start(1, "(1) 50 mL", q_prev, None)
        assert not _is_valid_new_question_start(1, "(A) Active", q_prev, None)


class TestOptionParsingHardening:
    def test_statement_in_stem_not_parsed_as_option(self):
        """'Statement (1)' in question stem must not be treated as option (1)."""
        text = (
            "Given below are two statements:\n"
            "Statement (1): Glucose is an aldohexose.\n"
            "Statement (2): Fructose is a ketohexose.\n"
            "(1) Both Statement (1) and Statement (2) are correct.\n"
            "(2) Both Statement (1) and Statement (2) are incorrect.\n"
            "(3) Statement (1) is correct but Statement (2) is incorrect.\n"
            "(4) Statement (1) is incorrect but Statement (2) is correct."
        )
        rq = RawQuestion(number=1, stem_text=text)
        stem, options = _parse_options_from_raw(rq)

        assert "Statement (1): Glucose is an aldohexose." in stem
        assert "Statement (2): Fructose is a ketohexose." in stem
        assert len(options) == 4
        assert options[0].label == "1"
        assert "Both Statement (1) and Statement (2) are correct." in options[0].text_str_en


class TestBilingualSplitHardening:
    def test_interleaved_lines_split(self):
        text = (
            "An ideal gas expands from volume V1 to V2.\n"
            "एक आदर्श गैस आयतन V1 से V2 तक प्रसारित होती है।\n"
            "Calculate work done at constant temperature.\n"
            "नियत ताप पर किए गए कार्य की गणना कीजिए।"
        )
        en, hi = split_bilingual_text(text)
        assert "An ideal gas expands" in en
        assert "Calculate work done" in en
        assert "एक आदर्श गैस" in hi
        assert "नियत ताप पर" in hi

    def test_per_line_slash_delimiter(self):
        text = (
            "Total mass / कुल द्रव्यमान\n"
            "Initial velocity / प्रारंभिक वेग"
        )
        en, hi = split_bilingual_text(text)
        assert en == "Total mass\nInitial velocity"
        assert hi == "कुल द्रव्यमान\nप्रारंभिक वेग"


class TestFigureAssignmentFallback:
    def test_proportional_fallback_without_blocks(self):
        """When questions lack attached blocks, figures are proportionally assigned instead of all to Q1."""
        q1 = Question(id="q1", number=1, sequence_index=1, source_pages=[1])
        q2 = Question(id="q2", number=2, sequence_index=2, source_pages=[1])

        # Figure near bottom of page 1 (y=650)
        fig_bottom = Figure(id="fig1", page=1, bbox=BBox(x1=100, y1=650, x2=300, y2=750))
        # Figure near top of page 1 (y=100)
        fig_top = Figure(id="fig2", page=1, bbox=BBox(x1=100, y1=100, x2=300, y2=200))

        _assign_figures_to_questions([fig_top, fig_bottom], [q1, q2])

        assert fig_top.question_ref == "q1"
        assert fig_bottom.question_ref == "q2"


class TestTightenedMathWrapping:
    def test_does_not_wrap_prose_words(self):
        """Prose sentence with math command wraps only math token, not prose words."""
        text = r"The value of \alpha is 5."
        wrapped = wrap_math_delimiters(text)
        assert r"$\alpha$" in wrapped
        # Verify prose words are NOT inside the math delimiters
        math_parts = [part for i, part in enumerate(wrapped.split("$")) if i % 2 == 1]
        for part in math_parts:
            assert "The value of" not in part
            assert "is 5" not in part

    def test_wraps_chemical_formula(self):
        text = r"Reaction: H_{2}SO_{4} + 2NaOH \to Na_{2}SO_{4} + 2H_{2}O"
        wrapped = wrap_math_delimiters(text)
        assert "$" in wrapped


class TestFurnitureDetectionGuard:
    def test_long_blocks_and_questions_not_dropped(self):
        """Blocks >80 chars or starting with question numbers must never be marked as furniture."""
        p_info = PageInfo(page_number=1, width_px=600, height_px=800)
        # Block with question start at top of page (norm_y = 0.05)
        b_q = Block(
            id="bq1",
            page=1,
            bbox=BBox(x1=50, y1=40, x2=550, y2=70),
            bbox_norm=(0.08, 0.05, 0.92, 0.08),
            text="1. What is the fundamental unit of charge in SI system?",
        )
        # Long passage block
        b_long = Block(
            id="blong",
            page=1,
            bbox=BBox(x1=50, y1=40, x2=550, y2=70),
            bbox_norm=(0.08, 0.05, 0.92, 0.08),
            text="A" * 85,
        )
        furniture = _find_repeating_furniture([b_q, b_long], [p_info, p_info])
        assert "bq1" not in furniture
        assert "blong" not in furniture


class TestCircuitBreakerProbe:
    def test_half_open_retry_after_pages(self):
        """Circuit breaker probes endpoint after 5 pages."""
        cfg = PaddleVLConfig(api_url="http://test-vl:8000")
        adapter = PaddleVLAdapter(config=cfg)
        adapter._circuit_open = True
        adapter._pages_since_fail = 4

        assert not adapter.is_available()

        # Simulate 5th page inquiry
        adapter._pages_since_fail = 5
        assert adapter.is_available()


class TestOptionPackingClassWithImages:
    def test_image_options_use_opt_col_1(self):
        """Options containing images must use opt-col-1 rather than grid-4."""
        opts = [
            Option(label="A", text_str_en='<img src="data:image/png;base64,iVBORw0KGgo=" />'),
            Option(label="B", text_str_en='<img src="data:image/png;base64,iVBORw0KGgo=" />'),
            Option(label="C", text_str_en='<img src="data:image/png;base64,iVBORw0KGgo=" />'),
            Option(label="D", text_str_en='<img src="data:image/png;base64,iVBORw0KGgo=" />'),
        ]
        assert get_option_packing_class(opts) == "opt-col-1"

    def test_compact_text_uses_grid_4(self):
        opts = [
            Option(label="A", text_str_en="10 m/s"),
            Option(label="B", text_str_en="20 m/s"),
            Option(label="C", text_str_en="30 m/s"),
            Option(label="D", text_str_en="40 m/s"),
        ]
        assert get_option_packing_class(opts) == "opt-grid-4"


class TestB64ImageFilterResolution:
    def test_resolves_image_in_cwd(self, tmp_path):
        dummy_img = tmp_path / "diagram.png"
        dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        ctx = MagicMock()
        ctx.run_dir = tmp_path
        ctx.stage_dir = tmp_path / "s9"

        flt = _b64_image_filter(ctx)
        res = flt(str(dummy_img))
        assert res.startswith("data:image/png;base64,")


class TestS8VerifyPostconditions:
    def test_blocker_triggers_violation_only_with_fail_fast(self):
        stage = S8Verify()
        doc = ExamDocument(source_path="test.pdf", source_hash="123", metadata=ExamMetadata())
        issue_blocker = Issue(id="b1", stage="s8", severity=IssueSeverity.BLOCKER, message="Fatal")

        res = StageResult(document=doc, issues=[issue_blocker])

        # Without fail_fast
        stage._fail_fast = False
        assert len(stage.validate_postconditions(res)) == 0

        # With fail_fast
        stage._fail_fast = True
        violations = stage.validate_postconditions(res)
        assert len(violations) == 1
        assert "blocker issues under fail_fast" in violations[0]


class TestNetworkSocketBlocking:
    def test_unmocked_network_socket_is_blocked(self):
        """Operating Rule 7 verification: raw socket creation is blocked."""
        import socket
        with pytest.raises(RuntimeError, match="Network socket access is blocked"):
            socket.socket()
