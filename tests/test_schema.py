"""Tests for the IR schema models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from examforge.ir.schema import (
    Answer,
    BBox,
    Block,
    BlockStatus,
    BlockType,
    EngineSource,
    ExamDocument,
    ExamMetadata,
    Figure,
    FigureClass,
    Issue,
    IssueSeverity,
    Lang,
    Option,
    PageClassification,
    PageInfo,
    PageStatus,
    Passage,
    Question,
    QuestionKind,
    Table,
    WatermarkTier,
)


class TestBBox:
    def test_basic_properties(self):
        box = BBox(x1=10, y1=20, x2=110, y2=220)
        assert box.width == 100
        assert box.height == 200
        assert box.area == 20000

    def test_overlap_ratio_identical(self):
        box = BBox(x1=0, y1=0, x2=100, y2=100)
        assert box.overlap_ratio(box) == 1.0

    def test_overlap_ratio_no_overlap(self):
        box1 = BBox(x1=0, y1=0, x2=50, y2=50)
        box2 = BBox(x1=100, y1=100, x2=150, y2=150)
        assert box1.overlap_ratio(box2) == 0.0

    def test_overlap_ratio_partial(self):
        box1 = BBox(x1=0, y1=0, x2=100, y2=100)
        box2 = BBox(x1=50, y1=50, x2=150, y2=150)
        ratio = box1.overlap_ratio(box2)
        # Intersection: 50×50 = 2500, Union: 10000 + 10000 - 2500 = 17500
        assert abs(ratio - 2500 / 17500) < 0.001


class TestBlock:
    def test_create_minimal(self):
        block = Block(
            id="b1",
            page=1,
            bbox=BBox(x1=0, y1=0, x2=100, y2=50),
        )
        assert block.id == "b1"
        assert block.page == 1
        assert block.type == BlockType.TEXT
        assert block.status == BlockStatus.TRUSTED
        assert block.text == ""
        assert block.sources == []

    def test_create_with_sources(self):
        block = Block(
            id="b2",
            page=1,
            bbox=BBox(x1=10, y1=10, x2=200, y2=30),
            text="Hello World",
            confidence=0.95,
            sources=[
                EngineSource(engine="paddleocr", text="Hello World", confidence=0.95),
                EngineSource(engine="tesseract", text="Hello Wrold", confidence=0.80),
            ],
            status=BlockStatus.DISPUTED,
        )
        assert len(block.sources) == 2
        assert block.sources[0].confidence == 0.95
        assert block.status == BlockStatus.DISPUTED

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Block(
                id="b3",
                page=1,
                bbox=BBox(x1=0, y1=0, x2=10, y2=10),
                confidence=1.5,  # Out of range
            )

    def test_dropped_with_reason(self):
        block = Block(
            id="b4",
            page=1,
            bbox=BBox(x1=0, y1=0, x2=50, y2=20),
            type=BlockType.WATERMARK,
            status=BlockStatus.DROPPED,
            drop_reason="Identified as repeating watermark text",
        )
        assert block.drop_reason is not None


class TestQuestion:
    def test_mcq_single(self):
        q = Question(
            id="q1",
            number=1,
            kind=QuestionKind.MCQ_SINGLE,
            options=[
                Option(label="A"),
                Option(label="B"),
                Option(label="C"),
                Option(label="D"),
            ],
        )
        assert len(q.options) == 4
        assert q.kind == QuestionKind.MCQ_SINGLE

    def test_with_answer(self):
        q = Question(
            id="q2",
            number=2,
            answer=Answer(correct_options=["B"]),
        )
        assert q.answer is not None
        assert q.answer.correct_options == ["B"]

    def test_numeric_answer(self):
        q = Question(
            id="q3",
            number=3,
            kind=QuestionKind.NUMERIC,
            answer=Answer(numeric_value=3.14, numeric_range=(3.10, 3.18)),
        )
        assert q.answer.numeric_value == 3.14

    def test_passage_reference(self):
        q = Question(
            id="q4",
            number=4,
            kind=QuestionKind.PASSAGE,
            passage_ref="passage_1",
            sub_question_refs=["q4a", "q4b"],
        )
        assert q.passage_ref == "passage_1"
        assert len(q.sub_question_refs) == 2


class TestPageInfo:
    def test_defaults(self):
        page = PageInfo(page_number=1)
        assert page.dpi is None
        assert page.classification == PageClassification.UNKNOWN
        assert page.watermark_tier == WatermarkTier.W0_NONE
        assert page.legacy_fonts == []

    def test_full_page_info(self):
        page = PageInfo(
            page_number=5,
            dpi=300.0,
            width_px=2480,
            height_px=3508,
            classification=PageClassification.QUESTIONS,
            has_text_layer=True,
            text_layer_valid=True,
            column_count=2,
            watermark_tier=WatermarkTier.W2_TRANSPARENT,
        )
        assert page.column_count == 2
        assert page.watermark_tier == WatermarkTier.W2_TRANSPARENT


class TestExamDocument:
    def test_empty_document(self):
        doc = ExamDocument(source_path="/test/exam.pdf")
        assert doc.pages == []
        assert doc.blocks == []
        assert doc.questions == []
        assert not doc.has_blockers()

    def test_add_issue(self):
        doc = ExamDocument(source_path="/test/exam.pdf")
        issue = Issue(
            id="test_1",
            stage="s0_intake",
            severity=IssueSeverity.WARNING,
            message="Test warning",
        )
        doc.add_issue(issue)
        assert len(doc.issues) == 1
        assert not doc.has_blockers()

    def test_blocker_detection(self):
        doc = ExamDocument(source_path="/test/exam.pdf")
        doc.add_issue(Issue(
            id="blocker_1",
            stage="s8_verify",
            severity=IssueSeverity.BLOCKER,
            rule="R01_no_furniture",
            message="Header found on page 3",
        ))
        assert doc.has_blockers()
        assert len(doc.blocker_issues()) == 1

    def test_resolved_blocker_not_counted(self):
        doc = ExamDocument(source_path="/test/exam.pdf")
        doc.add_issue(Issue(
            id="blocker_2",
            stage="s8_verify",
            severity=IssueSeverity.BLOCKER,
            message="Fixed",
            resolved=True,
        ))
        assert not doc.has_blockers()

    def test_get_page_blocks(self):
        doc = ExamDocument(source_path="/test/exam.pdf")
        doc.blocks = [
            Block(id="b1", page=1, bbox=BBox(x1=0, y1=0, x2=10, y2=10), order=2),
            Block(id="b2", page=1, bbox=BBox(x1=0, y1=20, x2=10, y2=30), order=1),
            Block(id="b3", page=2, bbox=BBox(x1=0, y1=0, x2=10, y2=10), order=1),
        ]
        p1_blocks = doc.get_page_blocks(1)
        assert len(p1_blocks) == 2
        assert p1_blocks[0].id == "b2"  # order=1 comes first
        assert p1_blocks[1].id == "b1"

    def test_serialization_roundtrip(self):
        """Document survives JSON serialization and deserialization."""
        doc = ExamDocument(
            source_path="/test/exam.pdf",
            source_hash="deadbeef",
            metadata=ExamMetadata(exam_name="NEET", year=2025),
            pages=[PageInfo(page_number=1, dpi=300.0)],
            blocks=[
                Block(
                    id="b1",
                    page=1,
                    bbox=BBox(x1=0, y1=0, x2=100, y2=50),
                    text="Hello",
                    sources=[EngineSource(engine="paddle", text="Hello", confidence=0.9)],
                ),
            ],
            questions=[
                Question(
                    id="q1",
                    number=1,
                    options=[Option(label="A"), Option(label="B")],
                ),
            ],
        )
        doc.add_issue(Issue(
            id="i1", stage="s0", severity=IssueSeverity.INFO, message="Test",
        ))

        # Serialize to JSON and back
        json_str = doc.model_dump_json(indent=2)
        data = json.loads(json_str)
        doc2 = ExamDocument(**data)

        assert doc2.source_path == doc.source_path
        assert doc2.metadata.exam_name == "NEET"
        assert len(doc2.pages) == 1
        assert len(doc2.blocks) == 1
        assert doc2.blocks[0].text == "Hello"
        assert len(doc2.questions) == 1
        assert doc2.questions[0].options[0].label == "A"
        assert len(doc2.issues) == 1


class TestFigure:
    def test_figure_model(self):
        fig = Figure(
            id="fig_1",
            page=3,
            bbox=BBox(x1=100, y1=200, x2=400, y2=500),
            classification=FigureClass.DIAGRAM,
            question_ref="q5",
        )
        assert fig.classification == FigureClass.DIAGRAM
        assert fig.status == BlockStatus.TRUSTED


class TestTable:
    def test_table_model(self):
        from examforge.ir.schema import Cell

        table = Table(
            id="t1",
            page=4,
            bbox=BBox(x1=50, y1=50, x2=500, y2=300),
            rows=[
                [Cell(text="A"), Cell(text="B")],
                [Cell(text="1"), Cell(text="2")],
            ],
        )
        assert len(table.rows) == 2
        assert table.rows[0][0].text == "A"


class TestPassage:
    def test_passage_model(self):
        passage = Passage(
            id="p1",
            question_refs=["q10", "q11", "q12"],
        )
        assert len(passage.question_refs) == 3
