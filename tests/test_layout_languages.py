"""Tests for language layout strategies and bilingual alignment (Phase 6.3)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import BBox, Block, IssueSeverity, Lang
from examforge.layout.languages import (
    AlignedBilingualQuestion,
    align_language_layout,
)


def _make_block(id: str, x1: float, y1: float, x2: float, y2: float, text: str, page: int = 1) -> Block:
    return Block(id=id, page=page, bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2), text=text)


class TestLanguageLayouts:
    def test_monolingual_layout(self):
        blocks = [
            _make_block("b1", 50, 50, 550, 100, "1. What is the speed of light?\n(A) 3e8 m/s\n(B) 2e8 m/s"),
            _make_block("b2", 50, 120, 550, 180, "2. State Ohm's law.\n(A) V=IR\n(B) V=I/R"),
        ]
        aligned, issues = align_language_layout(blocks, layout_mode="monolingual", primary_lang="en")
        assert len(issues) == 0
        assert len(aligned) == 2
        assert aligned[0].number == 1
        assert aligned[0].primary_text.startswith("1. What is the speed")
        assert aligned[0].secondary_text == ""

    def test_parallel_columns_layout(self):
        # Left col (English) vs Right col (Hindi)
        blocks = [
            # English question 1
            _make_block("en_q1", 40, 100, 280, 200, "1. The unit of force is:\n(1) Newton\n(2) Joule"),
            # Hindi question 1
            _make_block("hi_q1", 320, 100, 560, 200, "1. बल का मात्रक है:\n(1) न्यूटन\n(2) जूल"),
            # English question 2
            _make_block("en_q2", 40, 220, 280, 320, "2. Work done is:\n(1) Force x distance\n(2) Force / distance"),
            # Hindi question 2
            _make_block("hi_q2", 320, 220, 560, 320, "2. किया गया कार्य है:\n(1) बल x विस्थापन\n(2) बल / विस्थापन"),
        ]
        aligned, issues = align_language_layout(
            blocks,
            layout_mode="parallel_columns",
            primary_lang="en",
            secondary_lang="hi",
            page_width=600.0,
        )
        assert len(issues) == 0
        assert len(aligned) == 2
        assert aligned[0].number == 1
        assert "unit of force" in aligned[0].primary_text
        assert "बल का मात्रक" in aligned[0].secondary_text
        assert aligned[1].number == 2
        assert "Work done is" in aligned[1].primary_text
        assert "किया गया कार्य" in aligned[1].secondary_text

    def test_interleaved_layout(self):
        # Interleaved inside single stream
        blocks = [
            _make_block("q1", 50, 50, 550, 150, "1. Calculate momentum.\nसंवेग की गणना कीजिए।\n(1) mv\n(2) m/v"),
            _make_block("q2", 50, 160, 550, 260, "2. Define torque.\nबल आघूर्ण को परिभाषित कीजिए।\n(1) r x F\n(2) r . F"),
        ]
        aligned, issues = align_language_layout(
            blocks,
            layout_mode="interleaved",
            primary_lang="en",
            secondary_lang="hi",
        )
        assert len(issues) == 0
        assert len(aligned) == 2
        assert aligned[0].number == 1
        assert "Calculate momentum" in aligned[0].primary_text
        assert "संवेग की गणना" in aligned[0].secondary_text

    def test_separate_sections_layout(self):
        # English section on page 1, Hindi section on page 2
        blocks = [
            _make_block("en_q1", 50, 50, 550, 100, "1. English question one", page=1),
            _make_block("en_q2", 50, 120, 550, 180, "2. English question two", page=1),
            _make_block("hi_q1", 50, 50, 550, 100, "1. हिन्दी प्रश्न एक", page=2),
            _make_block("hi_q2", 50, 120, 550, 180, "2. हिन्दी प्रश्न दो", page=2),
        ]
        aligned, issues = align_language_layout(
            blocks,
            layout_mode="separate_sections",
            primary_lang="en",
            secondary_lang="hi",
        )
        assert len(issues) == 0
        assert len(aligned) == 2
        assert aligned[0].number == 1
        assert "English question one" in aligned[0].primary_text
        assert "हिन्दी प्रश्न एक" in aligned[0].secondary_text

    def test_mismatched_counts_emits_issue(self):
        # Left side has Q1, Q2, Q3; Right side only has Q1, Q2
        blocks = [
            _make_block("en_q1", 40, 100, 280, 150, "1. English 1"),
            _make_block("en_q2", 40, 160, 280, 210, "2. English 2"),
            _make_block("en_q3", 40, 220, 280, 270, "3. English 3"),
            _make_block("hi_q1", 320, 100, 560, 150, "1. हिन्दी 1"),
            _make_block("hi_q2", 320, 160, 560, 210, "2. हिन्दी 2"),
        ]
        aligned, issues = align_language_layout(
            blocks,
            layout_mode="parallel_columns",
            primary_lang="en",
            secondary_lang="hi",
            page_width=600.0,
        )
        assert len(aligned) == 3
        # Issue must be emitted for count mismatch
        assert any(i.severity == IssueSeverity.WARNING and "count mismatch" in i.message.lower() for i in issues)
