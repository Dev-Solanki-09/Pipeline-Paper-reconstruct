"""Tests for targeted gap re-search on sequence gaps."""

from __future__ import annotations

from examforge.ir.schema import BBox, Block, ExamDocument, PageInfo, Question
from examforge.repair.gap_search import gap_search_recover_question


def _make_doc_with_gap() -> ExamDocument:
    pages = [PageInfo(page_number=1, width_px=595, height_px=842)]
    # Q1 at y=10..50
    q1_block = Block(
        id="b1", page=1, bbox=BBox(x1=10, y1=10, x2=200, y2=50), text="1. First question"
    )
    q1 = Question(
        id="q1", number=1, stem_en=[q1_block], stem_text_en="1. First question", source_pages=[1]
    )

    # Unsegmented gap block at y=60..100 containing Q2!
    gap_block = Block(
        id="bgap",
        page=1,
        bbox=BBox(x1=10, y1=60, x2=200, y2=100),
        text="2. Recovered question in gap\n(A) Option A\n(B) Option B",
    )

    # Q3 at y=110..150
    q3_block = Block(
        id="b3", page=1, bbox=BBox(x1=10, y1=110, x2=200, y2=150), text="3. Third question"
    )
    q3 = Question(
        id="q3", number=3, stem_en=[q3_block], stem_text_en="3. Third question", source_pages=[1]
    )

    return ExamDocument(
        id="doc_gap",
        source_path="gap.pdf",
        pages=pages,
        blocks=[q1_block, gap_block, q3_block],
        questions=[q1, q3],  # Q2 is missing
    )


class TestGapSearch:
    def test_recover_missing_question_in_gap(self):
        doc = _make_doc_with_gap()
        recovered = gap_search_recover_question(doc, missing_number=2)

        assert recovered is not None
        assert recovered.number == 2
        assert "Recovered question" in recovered.stem_text_en
        assert len(recovered.options) == 2
        assert recovered.options[0].label == "A"
        assert recovered.options[1].label == "B"

    def test_return_none_when_no_blocks_in_gap(self):
        doc = _make_doc_with_gap()
        # Look for missing Q4 (no blocks after Q3)
        recovered = gap_search_recover_question(doc, missing_number=4)
        assert recovered is None
