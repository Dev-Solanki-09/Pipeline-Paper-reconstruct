"""Tests for document parts and page classification (Phase 6.8)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import BBox, Block, DocumentPart, PageClassification
from examforge.layout.parts import classify_document_part, classify_page_part


def _make_block(id: str, text: str, page: int = 1) -> Block:
    return Block(id=id, page=page, bbox=BBox(x1=50, y1=50, x2=550, y2=150), text=text)


class TestDocumentPartsClassification:
    def test_cover_page_detection(self):
        blocks = [
            _make_block("b1", "TEST BOOKLET - 2024\nCANDIDATE'S ROLL NUMBER: ______"),
            _make_block("b2", "Time Allowed: 3 Hours\nMaximum Marks: 720"),
            _make_block("b3", "DO NOT OPEN THIS BOOKLET UNTIL YOU ARE TOLD TO DO SO"),
        ]
        part = classify_page_part(blocks, page_num=1, total_pages=20)
        assert part == PageClassification.COVER

    def test_instructions_page_detection(self):
        blocks = [
            _make_block("b1", "IMPORTANT INSTRUCTIONS FOR CANDIDATES:"),
            _make_block("b2", "1. Immediately check that this Test Booklet contains 200 questions."),
            _make_block("b3", "2. Marking scheme: +4 marks for each correct answer, -1 for incorrect."),
        ]
        part = classify_page_part(blocks, page_num=2, total_pages=20)
        assert part == PageClassification.INSTRUCTIONS

    def test_questions_page_detection(self):
        blocks = [
            _make_block("b1", "SECTION - A (PHYSICS)"),
            _make_block("b2", "1. What is the dimension of Planck's constant?\n(1) [M L^2 T^-1]\n(2) [M L T^-1]"),
            _make_block("b3", "2. A particle moves in a circle...\n(1) 10 m/s\n(2) 20 m/s"),
        ]
        part = classify_page_part(blocks, page_num=3, total_pages=20)
        assert part == PageClassification.QUESTIONS

    def test_answer_key_page_detection(self):
        blocks = [
            _make_block("b1", "ANSWER KEY - FINAL"),
            _make_block("b2", "Q.No | Ans | Q.No | Ans\n1 | 2 | 26 | 4\n2 | 1 | 27 | 3"),
        ]
        part = classify_page_part(blocks, page_num=19, total_pages=20)
        assert part == PageClassification.ANSWER_KEY

    def test_rough_work_page_detection(self):
        blocks = [
            _make_block("b1", "SPACE FOR ROUGH WORK / रफ कार्य के लिए स्थान"),
        ]
        part = classify_page_part(blocks, page_num=20, total_pages=20)
        assert part == PageClassification.ROUGH_WORK
