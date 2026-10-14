"""
Tests for Phase O3: Pipeline Re-ordering & Stage Consolidation.

Verifies:
- O3.1: New DAG order: S0 Probe → S1 Profile → S2 Clean → S3 Parse → S4 Structure → S5 Normalize → S6 Figures → S8 Verify → S7 Repair → S9 Package
- O3.2: Cheap profiling input (S1 Profile uses source PDF text layer when blocks are not yet parsed)
- O3.3: Conditional cleaning with skip tracking & coordinate lock (geometry_final)
- O3.4: S5 Normalize merges S5 Math and S5 Hindi into a single question walk
- O3.5: Aliases for backwards compatibility (s5_math and s5_hindi map to s5_normalize)
- O3.6: Do-No-Harm invariant (digit multiset and unit multiset preservation)
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
    Option,
    PageClassification,
    PageInfo,
    Question,
)
from examforge.orchestrator.dag import STAGE_ORDER, STAGE_ALIASES, StageOrderList, resolve_stage_aliases
from examforge.profiles.fingerprint import extract_document_fingerprint
from examforge.stages.base import StageContext
from examforge.stages.s2_clean import S2Clean
from examforge.stages.s5_normalize import S5Normalize, _extract_digits, _extract_units


def test_o3_1_dag_order():
    """Verify new canonical DAG order matches Phase O3 spec."""
    expected_order = [
        "s0_intake",
        "s1_profile",
        "s2_clean",
        "s3_parse",
        "s4_structure",
        "s5_normalize",
        "s6_figures",
        "s8_verify",
        "s7_repair",
        "s9_package",
    ]
    assert list(STAGE_ORDER) == expected_order
    # Verify S2 clean comes before S3 parse
    assert STAGE_ORDER.index("s2_clean") < STAGE_ORDER.index("s3_parse")
    # Verify S8 verify comes before S7 repair
    assert STAGE_ORDER.index("s8_verify") < STAGE_ORDER.index("s7_repair")


def test_o3_2_stage_aliases():
    """Verify stage alias resolution and StageOrderList compatibility."""
    assert STAGE_ALIASES.get("s5_math") == "s5_normalize"
    assert STAGE_ALIASES.get("s5_hindi") == "s5_normalize"

    # StageOrderList transparent resolution
    assert STAGE_ORDER.index("s5_math") == STAGE_ORDER.index("s5_normalize")
    assert STAGE_ORDER.index("s5_hindi") == STAGE_ORDER.index("s5_normalize")
    assert "s5_math" in STAGE_ORDER
    assert "s5_hindi" in STAGE_ORDER

    # resolve_stage_aliases helper
    assert resolve_stage_aliases(["s0_intake", "s5_math"]) == ["s0_intake", "s5_normalize"]
    assert resolve_stage_aliases(["s5_hindi", "s5_math"]) == ["s5_normalize"]  # deduped


def test_o3_3_conditional_clean_skip_tracking(tmp_path: Path):
    """Verify S2 Clean skips unneeded steps and locks geometry_final."""
    # Create test PDF
    pdf_path = tmp_path / "test_clean.pdf"
    doc_pdf = pymupdf.open()
    page = doc_pdf.new_page(width=595, height=842)
    page.insert_text((50, 50), "Sample question text for clean stage test.")
    doc_pdf.save(str(pdf_path))
    doc_pdf.close()

    # Create ExamDocument before S3 Parse (doc.blocks empty)
    exam_doc = ExamDocument(
        schema_version=2,
        source_path=str(pdf_path),
        source_hash="hash_clean",
        metadata=ExamMetadata(exam_name="Clean Test"),
        pages=[PageInfo(page_number=1, width_px=595, height_px=842, classification=PageClassification.QUESTIONS)],
        blocks=[],
    )

    stage = S2Clean()
    ctx = StageContext(
        document=exam_doc,
        run_dir=tmp_path,
        config=None,
        spec=None,
        stage_dir=tmp_path / "s2",
    )
    result = stage.run(ctx)

    # Check metrics for skip reasons and geometry_final lock
    skip_reasons = result.metrics.get("skip_reasons", [])
    assert isinstance(skip_reasons, list)
    assert len(skip_reasons) > 0  # At least deskew_sub_threshold or watermark_tier_w0
    assert result.document.metadata.geometry_final is True


def test_o3_4_cheap_profiling_input(tmp_path: Path):
    """Verify S1 Profile fingerprint works when blocks are empty by reading PDF text layer."""
    pdf_path = tmp_path / "test_fingerprint.pdf"
    doc_pdf = pymupdf.open()
    page = doc_pdf.new_page(width=595, height=842)
    page.insert_text((50, 50), "Question 1: Find the value of x when 2x + 4 = 10.")
    doc_pdf.save(str(pdf_path))
    doc_pdf.close()

    exam_doc = ExamDocument(
        schema_version=2,
        source_path=str(pdf_path),
        source_hash="hash_fp",
        metadata=ExamMetadata(exam_name="FP Test"),
        pages=[PageInfo(page_number=1, width_px=595, height_px=842, classification=PageClassification.QUESTIONS)],
        blocks=[],  # Empty blocks (S1 before S3)
    )

    fp = extract_document_fingerprint(exam_doc)
    assert fp is not None
    assert fp.page_count_sampled == 1
    # Check that sample text was collected from the PDF text layer and analyzed
    assert fp.script_distribution.get("Latn", 0) > 0


def test_o3_5_unified_normalization(tmp_path: Path):
    """Verify S5 Normalize processes math and text normalization in a single question walk."""
    exam_doc = ExamDocument(
        schema_version=2,
        source_path="dummy.pdf",
        source_hash="hash_norm",
        metadata=ExamMetadata(exam_name="Norm Test"),
        pages=[PageInfo(page_number=1, width_px=595, height_px=842, classification=PageClassification.QUESTIONS)],
        blocks=[],
        questions=[
            Question(
                id="Q1",
                number=1,
                stem_text_en="Calculate 5 kg + 10 kg and find \\frac{1}{2} of 20 m/s.",
                options=[
                    Option(label="A", text_str_en="15 kg"),
                    Option(label="B", text_str_en="25 kg"),
                ],
            )
        ],
    )

    stage = S5Normalize()
    ctx = StageContext(
        document=exam_doc,
        run_dir=tmp_path,
        config=None,
        spec=None,
        stage_dir=tmp_path / "s5",
    )
    result = stage.run(ctx)

    assert result.metrics.get("s5_unified_normalized") is True
    # Digits and units preserved
    q = result.document.questions[0]
    assert "5" in q.stem_text_en and "10" in q.stem_text_en and "20" in q.stem_text_en
    assert "kg" in q.stem_text_en and "m/s" in q.stem_text_en


def test_o3_6_do_no_harm_invariant():
    """Verify digit multiset and unit multiset extractors and preservation check."""
    text1 = "A car moves 100 m/s with 50 kg mass in 20 s."
    digits1 = _extract_digits(text1)
    assert digits1["0"] == 4
    assert digits1["1"] == 1
    assert digits1["2"] == 1
    assert digits1["5"] == 1

    units1 = _extract_units(text1)
    assert units1["m/s"] == 1
    assert units1["kg"] == 1

    # Text with changed digits
    text2 = "A car moves 101 m/s with 50 kg mass in 20 s."
    digits2 = _extract_digits(text2)
    assert digits1 != digits2
