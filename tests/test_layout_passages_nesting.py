"""Tests for nesting subparts and passage detection & linking (Phases 6.5 and 6.6)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import BBox, Block, Passage
from examforge.layout.nesting import (
    detect_internal_choice,
    detect_subparts,
)
from examforge.layout.passages import (
    PassageSegment,
    detect_passages,
    link_questions_to_passages,
)


class TestNestingSubparts:
    def test_detect_subparts_alpha(self):
        text = (
            "Answer the following sub-questions:\n"
            "(a) Define electric flux.\n"
            "(b) State Gauss's law in electrostatics.\n"
            "(c) Derive Coulomb's law from Gauss's law."
        )
        subparts = detect_subparts(text, labels=["(a)", "(b)", "(c)", "(d)"])
        assert len(subparts) == 3
        assert [sp.label for sp in subparts] == ["(a)", "(b)", "(c)"]
        assert "Define electric flux" in subparts[0].text
        assert "State Gauss's law" in subparts[1].text
        assert "Derive Coulomb's law" in subparts[2].text

    def test_detect_subparts_roman(self):
        text = (
            "Evaluate:\n"
            "(i) lim_{x -> 0} sin(x)/x\n"
            "(ii) lim_{x -> infinity} (1 + 1/x)^x"
        )
        subparts = detect_subparts(text, labels=["(i)", "(ii)", "(iii)", "(iv)"])
        assert len(subparts) == 2
        assert [sp.label for sp in subparts] == ["(i)", "(ii)"]

    def test_detect_internal_choice_or(self):
        text_en = (
            "Derive the mirror formula for a concave mirror.\n"
            "OR\n"
            "Derive lens maker's formula for a double convex lens."
        )
        parts = detect_internal_choice(text_en)
        assert len(parts) == 2
        assert "mirror formula" in parts[0]
        assert "lens maker's formula" in parts[1]

    def test_detect_internal_choice_hindi_athwa(self):
        text_hi = (
            "अवतल दर्पण के लिए दर्पण सूत्र व्युत्पन्न कीजिए।\n"
            "अथवा\n"
            "उभयोत्तल लेंस के लिए लेंस निर्माता सूत्र व्युत्पन्न कीजिए।"
        )
        parts = detect_internal_choice(text_hi)
        assert len(parts) == 2
        assert "दर्पण सूत्र" in parts[0]
        assert "लेंस निर्माता सूत्र" in parts[1]


class TestPassageDetection:
    def test_detect_passage_header_and_range(self):
        blocks = [
            Block(
                id="p_head",
                page=3,
                bbox=BBox(x1=40, y1=50, x2=560, y2=80),
                text="Read the following comprehension passage and answer Questions 41 to 45:",
            ),
            Block(
                id="p_body",
                page=3,
                bbox=BBox(x1=40, y1=90, x2=560, y2=250),
                text="Photosynthesis is the biological process by which plants synthesize glucose...",
            ),
            Block(
                id="q41",
                page=3,
                bbox=BBox(x1=40, y1=270, x2=560, y2=350),
                text="41. Which organelle performs photosynthesis?",
            ),
        ]
        passages = detect_passages(blocks)
        assert len(passages) == 1
        psg = passages[0]
        assert psg.target_questions == [41, 42, 43, 44, 45]
        assert "Photosynthesis is the biological process" in psg.text

    def test_link_questions_to_passages(self):
        psg = PassageSegment(
            passage_id="pass_1",
            text="Comprehension text on thermodynamics.",
            target_questions=[15, 16, 17],
            source_pages=[2],
        )
        q_map = {14: "none", 15: "q15", 16: "q16", 17: "q17", 18: "none"}
        links = link_questions_to_passages([psg], [14, 15, 16, 17, 18])
        assert links[15] == "pass_1"
        assert links[16] == "pass_1"
        assert links[17] == "pass_1"
        assert 14 not in links
        assert 18 not in links
