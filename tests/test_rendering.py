"""Tests for HTML rendering with questions (Phase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    ExamDocument,
    ExamMetadata,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
)
from examforge.spec import Spec
from examforge.stages.base import StageContext
from examforge.stages.s9_package import S9Package


class TestHTMLRendering:
    def test_questions_appear_in_html(self, tmp_path):
        """Render a document with questions and verify they appear in the HTML."""
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="JEE Mock Exam", year=2026),
            pages=[
                PageInfo(page_number=1, classification=PageClassification.COVER),
                PageInfo(page_number=2, classification=PageClassification.QUESTIONS),
            ],
            questions=[
                Question(
                    id="q1",
                    number=1,
                    kind=QuestionKind.MCQ_SINGLE,
                    stem_text_en="Find the acceleration of the block.",
                    options=[
                        Option(label="A", text_str_en="9.8 m/s^2"),
                        Option(label="B", text_str_en="10 m/s^2"),
                        Option(label="C", text_str_en="5 m/s^2"),
                        Option(label="D", text_str_en="0 m/s^2"),
                    ],
                    source_pages=[2],
                )
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=Spec.default(),
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        result = stage.run(ctx)

        html_path = tmp_path / "output.html"
        assert html_path.exists()
        html_content = html_path.read_text(encoding="utf-8")

        assert "Q.1" in html_content or "1." in html_content
        assert "Find the acceleration of the block." in html_content
        assert "(A)" in html_content
        assert "9.8 m/s^2" in html_content
        assert "(B)" in html_content
        assert "10 m/s^2" in html_content

    def test_no_page_previews_when_questions_exist(self, tmp_path):
        """When questions > 0, page preview section should not appear."""
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="JEE Mock"),
            pages=[
                PageInfo(page_number=1, classification=PageClassification.QUESTIONS, image_path="page1.png"),
            ],
            questions=[
                Question(
                    id="q1",
                    number=1,
                    stem_text_en="Question stem text",
                    source_pages=[1],
                )
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=Spec.default(),
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        stage.run(ctx)

        html_content = (tmp_path / "output.html").read_text(encoding="utf-8")
        assert "Page Previews" not in html_content

    def test_page_previews_appear_when_no_questions(self, tmp_path):
        """When questions == 0, page preview section should appear."""
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="JEE Mock"),
            pages=[
                PageInfo(page_number=1, classification=PageClassification.QUESTIONS, image_path="page1.png"),
            ],
            questions=[],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=Spec.default(),
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        stage.run(ctx)

        html_content = (tmp_path / "output.html").read_text(encoding="utf-8")
        assert "Page Previews" in html_content

    def test_html_is_valid_structure(self, tmp_path):
        """Output HTML should have matching open/close structural tags."""
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="JEE Mock"),
            pages=[],
            questions=[],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=Spec.default(),
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        stage.run(ctx)

        html_content = (tmp_path / "output.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content and "</html>" in html_content
        assert "<head>" in html_content and "</head>" in html_content
        assert "<body>" in html_content and "</body>" in html_content

    def test_metadata_in_html_head(self, tmp_path):
        """Check that spec hash and exam name are in meta tags."""
        spec = Spec.default()
        exam_doc = ExamDocument(
            source_path="dummy.pdf",
            source_hash="dummy123",
            metadata=ExamMetadata(exam_name="Advanced Physics 2026", year=2026),
            pages=[],
            questions=[],
        )

        ctx = StageContext(
            document=exam_doc,
            config=ExamForgeConfig(),
            spec=spec,
            stage_dir=tmp_path / "s9",
            run_dir=tmp_path,
        )

        stage = S9Package()
        stage.run(ctx)

        html_content = (tmp_path / "output.html").read_text(encoding="utf-8")
        assert f'content="{spec.hash()}"' in html_content
        assert 'content="Advanced Physics 2026"' in html_content
        assert 'content="2026"' in html_content
