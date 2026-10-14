"""Tests for Phase 13.2 Deterministic Profile Inference."""

from __future__ import annotations

from examforge.ir.schema import BBox, Block, ExamDocument, PageClassification, PageInfo
from examforge.profiles.fingerprint import extract_document_fingerprint
from examforge.profiles.infer_rules import (
    ProfileInferenceResult,
    infer_profile_deterministic,
)


def _make_mock_doc(bilingual: bool, two_column: bool) -> ExamDocument:
    pages = [
        PageInfo(
            page_number=1,
            width_px=600,
            height_px=800,
            classification=PageClassification.QUESTIONS,
        )
    ]
    blocks = [
        Block(
            id="hdr",
            page=1,
            bbox=BBox(x1=50, y1=20, x2=550, y2=50),
            text="SECTION A - PHYSICS",
        )
    ]

    for i in range(1, 6):
        if two_column:
            # Left: English
            blocks.append(
                Block(
                    id=f"b_{i}_en",
                    page=1,
                    bbox=BBox(x1=50, y1=70 + i * 110, x2=280, y2=100 + i * 110),
                    text=f"Q.{i} What is the SI unit of power?",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_en_opts",
                    page=1,
                    bbox=BBox(x1=50, y1=105 + i * 110, x2=280, y2=135 + i * 110),
                    text="(A) Watt (B) Joule (C) Newton (D) Pascal",
                )
            )
            # Right: Hindi
            right_text = f"प्रश्न {i}. शक्ति की SI इकाई क्या है?" if bilingual else f"Q.{i} Power?"
            blocks.append(
                Block(
                    id=f"b_{i}_hi",
                    page=1,
                    bbox=BBox(x1=320, y1=70 + i * 110, x2=550, y2=100 + i * 110),
                    text=right_text,
                )
            )
        else:
            # Single column
            blocks.append(
                Block(
                    id=f"b_{i}",
                    page=1,
                    bbox=BBox(x1=50, y1=70 + i * 110, x2=550, y2=100 + i * 110),
                    text=f"{i}. Calculate total work done.",
                )
            )
            blocks.append(
                Block(
                    id=f"b_{i}_opts",
                    page=1,
                    bbox=BBox(x1=50, y1=105 + i * 110, x2=550, y2=135 + i * 110),
                    text="(1) 10 J (2) 20 J (3) 30 J (4) 40 J",
                )
            )

    return ExamDocument(source_path="mock.pdf", pages=pages, blocks=blocks)


def test_infer_monolingual_english_single_column():
    doc = _make_mock_doc(bilingual=False, two_column=False)
    fp = extract_document_fingerprint(doc)
    res = infer_profile_deterministic(doc, fp)

    assert isinstance(res, ProfileInferenceResult)
    p = res.profile
    assert len(p.languages) == 1
    assert p.languages[0].code == "en"
    assert p.language_layout == "monolingual"
    assert p.layout.columns == 1
    assert p.options.label_schemes == ["(1)", "(2)", "(3)", "(4)"]
    assert any(r"\d" in pat for pat in p.numbering.patterns)
    assert res.overall_confidence >= 0.85
    assert not res.low_confidence_fields


def test_infer_bilingual_parallel_two_column():
    doc = _make_mock_doc(bilingual=True, two_column=True)
    fp = extract_document_fingerprint(doc)
    res = infer_profile_deterministic(doc, fp)

    p = res.profile
    lang_codes = {lang.code for lang in p.languages}
    assert "en" in lang_codes
    assert "hi" in lang_codes
    assert p.language_layout == "parallel_columns"
    assert p.layout.columns == 2
    assert p.options.label_schemes == ["(A)", "(B)", "(C)", "(D)"]
    assert res.field_confidences["languages"] >= 0.9
    assert res.field_confidences["language_layout"] >= 0.85
    assert res.overall_confidence >= 0.85


def test_infer_sparse_document_flags_low_confidence():
    # Only 1 block, no options, no obvious numbering
    sparse_doc = ExamDocument(
        source_path="sparse.pdf",
        pages=[PageInfo(page_number=1, width_px=600, height_px=800)],
        blocks=[Block(id="b1", page=1, bbox=BBox(x1=10, y1=10, x2=200, y2=40), text="Hello World")],
    )
    fp = extract_document_fingerprint(sparse_doc)
    res = infer_profile_deterministic(sparse_doc, fp, confidence_threshold=0.85)

    assert len(res.low_confidence_fields) > 0
    assert (
        "options.label_schemes" in res.low_confidence_fields
        or "numbering.patterns" in res.low_confidence_fields
    )
