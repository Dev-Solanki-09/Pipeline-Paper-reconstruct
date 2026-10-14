"""Tests for S3 Parse stage (text block extraction)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from examforge.ir.schema import (
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Lang,
    PageClassification,
    PageInfo,
)
from examforge.stages.base import StageContext
from examforge.stages.s0_intake import S0Intake
from examforge.stages.s3_parse import (
    S3Parse,
    _detect_block_language,
    _extract_blocks_from_page,
)


class TestDetectBlockLanguage:
    def test_english_text(self):
        assert _detect_block_language("The mass of the object is 5 kg") == Lang.EN

    def test_hindi_text(self):
        assert _detect_block_language("वस्तु का द्रव्यमान 5 kg है") == Lang.HI

    def test_mixed_defaults_to_english(self):
        """If <30% Devanagari, classify as English."""
        assert _detect_block_language("Force = 10 N बल") == Lang.EN

    def test_empty_string(self):
        assert _detect_block_language("") == Lang.UNKNOWN

    def test_numbers_only(self):
        assert _detect_block_language("12345") == Lang.EN


class TestExtractBlocksFromPage:
    def test_extracts_text_blocks(self, sample_pdf_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        doc = pymupdf.open(str(sample_pdf_path))
        page = doc[1]  # Page 2 (0-indexed 1)
        blocks, counter = _extract_blocks_from_page(page, page_num=2, block_counter=0, page_width_px=612, page_height_px=792)
        doc.close()

        assert len(blocks) >= 5

    def test_block_ids_are_unique(self, sample_pdf_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        doc = pymupdf.open(str(sample_pdf_path))
        all_blocks: list[Block] = []
        counter = 0
        for p_idx in range(3):
            page = doc[p_idx]
            p_blocks, counter = _extract_blocks_from_page(page, page_num=p_idx + 1, block_counter=counter, page_width_px=600, page_height_px=800)
            all_blocks.extend(p_blocks)
        doc.close()

        ids = [b.id for b in all_blocks]
        assert len(ids) == len(set(ids))

    def test_block_has_bbox(self, sample_pdf_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        doc = pymupdf.open(str(sample_pdf_path))
        page = doc[1]
        blocks, _ = _extract_blocks_from_page(page, page_num=2, block_counter=0, page_width_px=612, page_height_px=792)
        doc.close()

        for b in blocks:
            assert b.bbox.width > 0
            assert b.bbox.height > 0

    def test_block_text_not_empty(self, sample_pdf_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        doc = pymupdf.open(str(sample_pdf_path))
        page = doc[1]
        blocks, _ = _extract_blocks_from_page(page, page_num=2, block_counter=0, page_width_px=612, page_height_px=792)
        doc.close()

        for b in blocks:
            assert len(b.text.strip()) > 0

    def test_block_confidence_is_one(self, sample_pdf_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")
        doc = pymupdf.open(str(sample_pdf_path))
        page = doc[1]
        blocks, _ = _extract_blocks_from_page(page, page_num=2, block_counter=0, page_width_px=612, page_height_px=792)
        doc.close()

        for b in blocks:
            assert b.confidence == 1.0
            assert b.status == BlockStatus.TRUSTED


class TestS3ParseStage:
    def test_skips_pages_without_text_layer(self, tmp_path):
        pdf_path = tmp_path / "dummy.pdf"
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Hello world")
        doc.save(str(pdf_path))
        doc.close()

        exam_doc = ExamDocument(
            source_path=str(pdf_path),
            source_hash="dummy_hash",
            metadata=ExamMetadata(exam_name="Dummy"),
            pages=[
                PageInfo(
                    page_number=1,
                    has_text_layer=False,
                    text_layer_valid=False,
                    classification=PageClassification.QUESTIONS,
                ),
            ],
        )
        ctx = StageContext(
            document=exam_doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s3",
            run_dir=tmp_path,
        )

        stage = S3Parse()
        result = stage.run(ctx)
        assert len(result.document.blocks) == 0
        assert result.metrics["pages_skipped"] == 1

    def test_requires_pages_precondition(self, empty_document, tmp_path):
        ctx = StageContext(
            document=empty_document,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s3",
            run_dir=tmp_path,
        )
        stage = S3Parse()
        violations = stage.validate_preconditions(ctx)
        assert len(violations) > 0

    def test_end_to_end_with_sample_pdf(self, sample_pdf_path, tmp_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")

        # Create document with 2 pages to keep test fast
        doc = pymupdf.open(str(sample_pdf_path))
        exam_doc = ExamDocument(
            source_path=str(sample_pdf_path),
            source_hash="sample_hash",
            metadata=ExamMetadata(exam_name="JEE Adv"),
            pages=[
                PageInfo(
                    page_number=1,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.COVER,
                    width_px=612,
                    height_px=792,
                ),
                PageInfo(
                    page_number=2,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.QUESTIONS,
                    width_px=612,
                    height_px=792,
                ),
            ],
        )
        doc.close()

        ctx = StageContext(
            document=exam_doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s3",
            run_dir=tmp_path,
        )
        stage = S3Parse()
        result = stage.run(ctx)

        assert len(result.document.blocks) >= 10
        assert result.metrics["total_blocks"] >= 10
        assert result.metrics["early_exit_pages"] == 1
        post_violations = stage.validate_postconditions(result)
        assert len(post_violations) == 0
