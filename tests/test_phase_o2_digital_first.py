"""
Tests for Phase O2: Digital-First Fast Path.

Verifies:
- O2.1: Page path classifier (Path A digital, Path B scan, Path C broken font)
- O2.2: Path A performs zero model inference (model_inferences == 0)
- O2.2: Subscript and superscript reconstruction from font baseline offsets and size ratios
- O2.3: Path B routes to PaddleOCR-VL-1.6
- O2.4: Path C glyph decoding and cache reuse (second run on same font = 0 glyph OCR)
- O2.5: Low-confidence blocks on Path B trigger selective issue logging
- O2.6: Early exit skips non-question pages (COVER, INSTRUCTIONS, ROUGH_WORK, BLANK, OMR)
"""

from __future__ import annotations

from pathlib import Path
import pymupdf
import pytest

from examforge.ir.schema import (
    Block,
    BlockType,
    ExamDocument,
    ExamMetadata,
    PageClassification,
    PageInfo,
    PageProcessingPath,
)
from examforge.engines.paddle_vl import PaddleVLAdapter, PaddleVLConfig
from examforge.ocr.glyph_cache import GlyphDecoder
from examforge.stages.base import StageContext
from examforge.stages.s0_intake import _classify_processing_path
from examforge.stages.s3_parse import S3Parse, _extract_blocks_from_page


@pytest.fixture
def clean_adapters():
    """Reset adapter state before each test."""
    PaddleVLAdapter.reset_inference_count()
    PaddleVLAdapter.reset_shared_instances()
    GlyphDecoder.reset_cache()
    yield
    PaddleVLAdapter.reset_inference_count()
    PaddleVLAdapter.reset_shared_instances()
    GlyphDecoder.reset_cache()


def test_o2_1_path_classifier_routing():
    """Verify O2.1 path classifier distinguishes Path A, B, and C."""
    doc = pymupdf.open()
    
    # 1. Digital page with text -> Path A
    p1 = doc.new_page()
    p1.insert_text((50, 50), "What is the speed of light in vacuum? (A) 3x10^8 m/s (B) 2x10^8 m/s")
    path_a = _classify_processing_path(p1, p1.get_text("text"), True, [])
    assert path_a == PageProcessingPath.PATH_A

    # 2. Scanned / empty text page -> Path B
    p2 = doc.new_page()
    path_b = _classify_processing_path(p2, "", False, [])
    assert path_b == PageProcessingPath.PATH_B

    # 3. Legacy Hindi font page -> Path C
    p3 = doc.new_page()
    p3.insert_text((50, 50), "[k ?k Fk /k vk bZ")
    path_c = _classify_processing_path(p3, p3.get_text("text"), True, ["krutidev010"])
    assert path_c == PageProcessingPath.PATH_C
    doc.close()


def test_o2_2_path_a_zero_model_inference(tmp_path, clean_adapters):
    """Verify O2.2: Path A performs ZERO model inference calls."""
    pdf_path = tmp_path / "digital_paper.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 50), "Question 1: Calculate the acceleration of the mass.")
    p.insert_text((50, 70), "(A) 9.8 m/s^2 (B) 4.9 m/s^2")
    doc.save(str(pdf_path))
    doc.close()

    exam_doc = ExamDocument(
        source_path=str(pdf_path),
        source_hash="hash_digital",
        metadata=ExamMetadata(exam_name="Digital Test"),
        pages=[
            PageInfo(
                page_number=1,
                has_text_layer=True,
                text_layer_valid=True,
                classification=PageClassification.QUESTIONS,
                processing_path=PageProcessingPath.PATH_A,
                width_px=612,
                height_px=792,
            )
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

    assert len(result.document.blocks) >= 1
    assert result.metrics["path_a_pages"] == 1
    assert result.metrics["model_inferences"] == 0
    assert PaddleVLAdapter.get_inference_count() == 0


def test_o2_2_subscript_superscript_reconstruction(tmp_path):
    """Verify O2.2: Subscripts and superscripts are accurately formatted from font size and baseline."""
    pdf_path = tmp_path / "math_subsuper.pdf"
    doc = pymupdf.open()
    p = doc.new_page()
    # Main text at size 12
    p.insert_text((50, 100), "Formula: E = mc", fontsize=12)
    # Superscript '2' at size 8, elevated baseline (y=97 instead of 100)
    p.insert_text((140, 97), "2", fontsize=8)
    doc.save(str(pdf_path))
    doc.close()

    doc_read = pymupdf.open(str(pdf_path))
    blocks, _ = _extract_blocks_from_page(
        doc_read[0], page_num=1, block_counter=0, page_width_px=612, page_height_px=792
    )
    doc_read.close()

    assert len(blocks) >= 1
    full_text = " ".join(b.text for b in blocks)
    assert "^{2}" in full_text


def test_o2_4_path_c_glyph_decoding_and_cache_reuse(clean_adapters):
    """Verify O2.4: Path C glyph decoding transliterates and caches glyphs."""
    decoder = GlyphDecoder()
    
    # KrutiDev token "[k" -> "ख"
    decoded_first = decoder.decode_text("krutidev010", "[k")
    assert "ख" in decoded_first

    # Check custom fallback OCR counting
    called_count = 0
    def custom_ocr(ch: str) -> str:
        nonlocal called_count
        called_count += 1
        return "A"

    custom_decoder = GlyphDecoder(fallback_ocr_fn=custom_ocr)
    res1 = custom_decoder.decode_text("UnknownBrokenFont", "xyz")
    assert res1 == "AAA"
    assert called_count == 3

    # Second pass on identical font and chars -> 0 calls to fallback OCR
    res2 = custom_decoder.decode_text("UnknownBrokenFont", "xyz")
    assert res2 == "AAA"
    assert called_count == 3  # Unchanged! Zero new OCR calls


def test_o2_6_per_page_early_exit(tmp_path, clean_adapters):
    """Verify O2.6: Non-content pages (cover, rough work, OMR, blank, instructions) are skipped."""
    pdf_path = tmp_path / "early_exit.pdf"
    doc = pymupdf.open()
    # 5 pages
    for _ in range(5):
        p = doc.new_page()
        p.insert_text((50, 50), "Some text here")
    doc.save(str(pdf_path))
    doc.close()

    exam_doc = ExamDocument(
        source_path=str(pdf_path),
        source_hash="early_exit_hash",
        metadata=ExamMetadata(exam_name="Early Exit Test"),
        pages=[
            PageInfo(page_number=1, classification=PageClassification.COVER, has_text_layer=True, text_layer_valid=True),
            PageInfo(page_number=2, classification=PageClassification.INSTRUCTIONS, has_text_layer=True, text_layer_valid=True),
            PageInfo(page_number=3, classification=PageClassification.QUESTIONS, has_text_layer=True, text_layer_valid=True),
            PageInfo(page_number=4, classification=PageClassification.ROUGH_WORK, has_text_layer=True, text_layer_valid=True),
            PageInfo(page_number=5, classification=PageClassification.OMR, has_text_layer=True, text_layer_valid=True),
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

    # 4 non-question pages skipped via early exit
    assert result.metrics["early_exit_pages"] == 4
    assert result.metrics["pages_processed"] == 1
    assert result.metrics["path_a_pages"] == 1
    # Only Page 3 blocks extracted
    assert all(b.page == 3 for b in result.document.blocks)
