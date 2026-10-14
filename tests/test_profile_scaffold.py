"""Tests for Phase 13.4 & 13.5 Profile Scaffolding & Preview Generator."""

from __future__ import annotations

from pathlib import Path

import yaml

from examforge.ir.schema import BBox, Block, ExamDocument, PageClassification, PageInfo
from examforge.profiles.scaffold import scaffold_profile
from examforge.profiles.schema import ExamProfile


def _make_test_doc() -> ExamDocument:
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
            text="AIIMS ENTRANCE EXAMINATION",
        ),
        Block(
            id="q1",
            page=1,
            bbox=BBox(x1=50, y1=80, x2=550, y2=110),
            text="1. Which organ produces insulin?",
        ),
        Block(
            id="q1_opts",
            page=1,
            bbox=BBox(x1=50, y1=115, x2=550, y2=145),
            text="(1) Liver (2) Pancreas (3) Kidney (4) Stomach",
        ),
    ]
    return ExamDocument(source_path="mock_exam.pdf", pages=pages, blocks=blocks)


def test_scaffold_generates_yaml_and_html(tmp_path: Path):
    doc = _make_test_doc()
    yaml_path, html_path, profile, low_conf = scaffold_profile(
        doc=doc,
        output_dir=tmp_path,
        profile_id="aiims_test",
    )

    assert yaml_path.exists()
    assert html_path.exists()
    assert yaml_path.suffix == ".yaml"
    assert html_path.suffix == ".html"

    # Verify YAML content
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["id"] == "aiims_test"
    assert data["maturity"] == "experimental"
    loaded_prof = ExamProfile.model_validate(data)
    assert loaded_prof.id == "aiims_test"

    # Verify HTML preview content
    html_content = html_path.read_text(encoding="utf-8")
    assert "Profile Preview: aiims_test" in html_content
    assert "Which organ produces insulin?" in html_content or "q1" in html_content
    assert "overlay" in html_content or "gutter" in html_content
