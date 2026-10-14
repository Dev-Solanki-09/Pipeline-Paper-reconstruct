"""Tests for S2 Clean stage (furniture, page numbers, branding removal)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Lang,
    PageClassification,
    PageInfo,
)
from examforge.stages.base import StageContext, StageResult
from examforge.stages.s2_clean import (
    S2Clean,
    _detect_branding,
    _detect_page_numbers,
    _find_repeating_furniture,
)


def _make_block(
    block_id: str,
    page: int,
    text: str,
    bbox_norm: tuple[float, float, float, float] | None = None,
) -> Block:
    return Block(
        id=block_id,
        page=page,
        type=BlockType.TEXT,
        bbox=BBox(x1=50, y1=50, x2=500, y2=100),
        bbox_norm=bbox_norm or (0.1, 0.1, 0.9, 0.2),
        order=0,
        lang=Lang.EN,
        text=text,
        confidence=1.0,
        status=BlockStatus.TRUSTED,
    )


class TestS2CleanFurniture:
    def test_precondition_requires_blocks(self, empty_document, tmp_path):
        ctx = StageContext(
            document=empty_document,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s2",
            run_dir=tmp_path,
        )
        stage = S2Clean()
        violations = stage.validate_preconditions(ctx)
        assert len(violations) > 0

    def test_drops_space_for_rough_work(self, tmp_path):
        b1 = _make_block("b1", page=1, text="SPACE FOR ROUGH WORK", bbox_norm=(0.1, 0.92, 0.9, 0.98))
        b2 = _make_block("b2", page=1, text="1. An object starts from rest...", bbox_norm=(0.1, 0.2, 0.9, 0.3))

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            blocks=[b1, b2],
        )

        ctx = StageContext(document=doc, config=None, spec=None, stage_dir=tmp_path / "s2", run_dir=tmp_path)
        stage = S2Clean()
        result = stage.run(ctx)

        assert b1.status == BlockStatus.DROPPED
        assert b1.type == BlockType.FOOTER
        assert b1.drop_reason is not None and "Footer furniture" in b1.drop_reason
        assert b2.status == BlockStatus.TRUSTED
        assert result.metrics["blocks_dropped"] == 1

    def test_detect_branding(self):
        b_url = _make_block("b_url", page=1, text="Visit https://www.allen.ac.in for details")
        b_phone = _make_block("b_phone", page=1, text="Call 9876543210 for support")
        b_clean = _make_block("b_clean", page=1, text="Find the magnetic flux through the ring")

        branded_ids = _detect_branding([b_url, b_phone, b_clean])
        assert "b_url" in branded_ids
        assert "b_phone" in branded_ids
        assert "b_clean" not in branded_ids

    def test_detect_page_numbers(self):
        b_p1 = _make_block("b_p1", page=1, text="1", bbox_norm=(0.48, 0.95, 0.52, 0.98))
        b_p2 = _make_block("b_p2", page=2, text="2", bbox_norm=(0.48, 0.95, 0.52, 0.98))
        b_q = _make_block("b_q", page=1, text="1. Calculate the work done", bbox_norm=(0.1, 0.2, 0.9, 0.3))

        pn_ids = _detect_page_numbers([b_p1, b_p2, b_q])
        assert "b_p1" in pn_ids
        assert "b_p2" in pn_ids
        assert "b_q" not in pn_ids

    def test_postcondition_guarantee_g2(self, tmp_path):
        """No block can be dropped without a drop reason."""
        b_bad = _make_block("b_bad", page=1, text="Header")
        b_bad.status = BlockStatus.DROPPED
        b_bad.drop_reason = None  # Violation

        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1)],
            blocks=[b_bad],
        )

        ctx = StageContext(document=doc, config=None, spec=None, stage_dir=tmp_path / "s2", run_dir=tmp_path)
        stage = S2Clean()
        violations = stage.validate_postconditions(StageResult(document=doc, metrics={}, issues=[]))
        assert len(violations) > 0
        assert "drop_reason" in violations[0]

    def test_clean_v2_rollback_flag(self, tmp_path):
        """Setting clean_v2=False rolls back to v1 cleaning logic."""
        from examforge.profiles.schema import ExamProfile

        b_footer = _make_block("bf", page=1, text="SPACE FOR ROUGH WORK", bbox_norm=(0.1, 0.92, 0.9, 0.98))
        doc = ExamDocument(
            source_path="test.pdf",
            source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            blocks=[b_footer],
        )

        profile_v1 = ExamProfile(
            id="clean_v1_prof",
            name="clean_v1_prof",
            description="Testing v1 rollback",
            flags={"clean_v2": False},
        )

        ctx = StageContext(
            document=doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s2_v1",
            run_dir=tmp_path,
            profile=profile_v1,
        )

        stage = S2Clean()
        result = stage.run(ctx)
        assert b_footer.status == BlockStatus.DROPPED
        assert result.metrics["blocks_dropped"] == 1
