"""Tests for Phase 13.1 Profile Fingerprint & Cache."""

from __future__ import annotations

from pathlib import Path

from examforge.ir.schema import BBox, Block, ExamDocument, PageClassification, PageInfo
from examforge.profiles.fingerprint import (
    DocumentFingerprint,
    ProfileCache,
    extract_document_fingerprint,
)


def _make_sample_doc(
    bilingual: bool = False,
    two_column: bool = False,
    num_pages: int = 2,
) -> ExamDocument:
    pages = [
        PageInfo(
            page_number=p,
            width_px=600,
            height_px=800,
            classification=PageClassification.QUESTIONS,
        )
        for p in range(1, num_pages + 1)
    ]
    blocks = []
    for p in range(1, num_pages + 1):
        # Header block in top 10%
        blocks.append(
            Block(
                id=f"hdr_{p}",
                page=p,
                bbox=BBox(x1=50, y1=20, x2=550, y2=60),
                text="NATIONAL ENTRANCE TEST 2026",
            )
        )
        for i in range(1, 6):
            q_num = (p - 1) * 5 + i
            if two_column:
                # Column 1 (Left)
                blocks.append(
                    Block(
                        id=f"b_{p}_{q_num}_col1",
                        page=p,
                        bbox=BBox(x1=50, y1=100 + i * 100, x2=280, y2=130 + i * 100),
                        text=f"Q.{q_num} What is velocity?",
                    )
                )
                blocks.append(
                    Block(
                        id=f"b_{p}_{q_num}_opts1",
                        page=p,
                        bbox=BBox(x1=50, y1=135 + i * 100, x2=280, y2=165 + i * 100),
                        text="(A) 10 m/s (B) 20 m/s",
                    )
                )
                # Column 2 (Right)
                right_text = f"प्रश्न {q_num}. वेग क्या है?" if bilingual else f"Q.{q_num} Acceleration?"
                blocks.append(
                    Block(
                        id=f"b_{p}_{q_num}_col2",
                        page=p,
                        bbox=BBox(x1=320, y1=100 + i * 100, x2=550, y2=130 + i * 100),
                        text=right_text,
                    )
                )
            else:
                # Single column
                blocks.append(
                    Block(
                        id=f"b_{p}_{q_num}",
                        page=p,
                        bbox=BBox(x1=50, y1=100 + i * 100, x2=550, y2=130 + i * 100),
                        text=f"{q_num}. Calculate force.",
                    )
                )
                blocks.append(
                    Block(
                        id=f"b_{p}_{q_num}_opts",
                        page=p,
                        bbox=BBox(x1=50, y1=135 + i * 100, x2=550, y2=165 + i * 100),
                        text="(1) 5 N (2) 10 N (3) 15 N (4) 20 N",
                    )
                )

    return ExamDocument(source_path="mock_exam.pdf", pages=pages, blocks=blocks)


def test_extract_fingerprint_monolingual_single_column():
    doc = _make_sample_doc(bilingual=False, two_column=False)
    fp = extract_document_fingerprint(doc, max_pages=2)

    assert isinstance(fp, DocumentFingerprint)
    assert fp.estimated_columns == 1
    assert fp.dominant_numbering == "dot"
    assert fp.dominant_option_scheme == "digit_paren"
    assert fp.script_distribution.get("Latn", 0.0) > 0.9
    assert fp.script_distribution.get("Deva", 0.0) == 0.0
    assert fp.header_hash != ""
    assert len(fp.doc_hash) == 32 or len(fp.doc_hash) == 64


def test_extract_fingerprint_bilingual_two_column():
    doc = _make_sample_doc(bilingual=True, two_column=True)
    fp = extract_document_fingerprint(doc, max_pages=2)

    assert fp.estimated_columns == 2
    assert len(fp.gutters) >= 1
    # Gutter should be around center (x ~ 280-320 normalized or absolute)
    assert any(270 <= g <= 330 for g in fp.gutters)
    assert fp.dominant_numbering == "q_prefix"
    assert fp.dominant_option_scheme == "alpha_paren"
    assert fp.script_distribution.get("Latn", 0.0) > 0.3
    assert fp.script_distribution.get("Deva", 0.0) > 0.3


def test_profile_cache_operations(tmp_path: Path):
    db_path = tmp_path / "test_cache.sqlite"
    cache = ProfileCache(db_path)

    # Initial lookup returns None
    assert cache.lookup("fp_123456") is None

    # Store a proposal
    cache.store(
        fingerprint_hash="fp_123456",
        profile_id="neet_ug",
        profile_yaml="id: neet_ug\nname: NEET-UG\n",
        confidence=0.98,
    )

    res = cache.lookup("fp_123456")
    assert res is not None
    p_id, p_yaml, conf, hits = res
    assert p_id == "neet_ug"
    assert "NEET-UG" in p_yaml
    assert conf == 0.98
    assert hits == 1

    # Record hit
    cache.record_hit("fp_123456")
    _, _, _, updated_hits = cache.lookup("fp_123456")
    assert updated_hits == 2
