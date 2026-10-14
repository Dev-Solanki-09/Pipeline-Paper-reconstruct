"""
Unit tests for ExamForge Exporters (Phase 14.6).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.export import (
    HTMLExporter,
    JSONExporter,
    JSONLExporter,
    MarkdownExporter,
    QTIExporter,
    get_exporter,
    list_exporters,
)
from examforge.ir.schema import (
    AnswerSpec,
    BlankNode,
    Cell,
    CodeNode,
    ExamDocument,
    ExamMetadata,
    FigureNode,
    Marks,
    MatchColumnsNode,
    MathNode,
    Option,
    PageClassification,
    PageInfo,
    Question,
    QuestionKind,
    RawCropNode,
    StatementsNode,
    TableNode,
    TextNode,
)
from examforge.spec import Spec
from examforge.stages.base import StageContext
from examforge.stages.s9_package import S9Package


@pytest.fixture
def sample_exam_document() -> ExamDocument:
    return ExamDocument(
        source_path="mock_exam.pdf",
        source_hash="sha256_mock_123",
        metadata=ExamMetadata(
            exam_name="National Entrance Examination",
            year=2026,
            subject="Physics & Chemistry",
            series_code="SET-A",
        ),
        pages=[
            PageInfo(page_number=1, classification=PageClassification.COVER),
            PageInfo(page_number=2, classification=PageClassification.QUESTIONS),
        ],
        questions=[
            Question(
                id="q1",
                number=1,
                section="Physics",
                kind=QuestionKind.SINGLE_CORRECT,
                stem=[
                    TextNode(texts={"en": "What is the unit of force in SI?"}),
                    MathNode(code=r"F = m \cdot a", display=False),
                ],
                options=[
                    Option(label="A", content=[TextNode(texts={"en": "Newton"})]),
                    Option(label="B", content=[TextNode(texts={"en": "Joule"})]),
                    Option(label="C", content=[TextNode(texts={"en": "Pascal"})]),
                    Option(label="D", content=[TextNode(texts={"en": "Watt"})]),
                ],
                answer=AnswerSpec(correct_options=["A"]),
                marks=Marks(positive=4.0, negative=1.0),
                source_pages=[2],
            ),
            Question(
                id="q2",
                number=2,
                section="Physics",
                kind=QuestionKind.MULTI_CORRECT,
                stem=[
                    TextNode(texts={"en": "Which of the following are vector quantities?"}),
                ],
                options=[
                    Option(label="A", content=[TextNode(texts={"en": "Velocity"})]),
                    Option(label="B", content=[TextNode(texts={"en": "Acceleration"})]),
                    Option(label="C", content=[TextNode(texts={"en": "Speed"})]),
                    Option(label="D", content=[TextNode(texts={"en": "Displacement"})]),
                ],
                answer=AnswerSpec(correct_options=["A", "B", "D"]),
                source_pages=[2],
            ),
            Question(
                id="q3",
                number=3,
                section="Physics",
                kind=QuestionKind.NUMERICAL,
                stem=[
                    TextNode(
                        texts={
                            "en": (
                                "Calculate the value of acceleration due to gravity in m/s^2:"
                            )
                        }
                    ),
                    MathNode(code=r"g = \frac{G M}{R^2}", display=True),
                ],
                answer=AnswerSpec(numeric_value=9.8),
                source_pages=[2],
            ),
            Question(
                id="q4",
                number=4,
                section="Chemistry",
                kind=QuestionKind.MATCH,
                stem=[
                    TextNode(texts={"en": "Match Column I with Column II:"}),
                    MatchColumnsNode(
                        left=[{"A": "Methane"}, {"B": "Ethene"}],
                        right=[{"P": "Alkene"}, {"Q": "Alkane"}],
                    ),
                    TableNode(
                        rows=[
                            [Cell(text="Compound"), Cell(text="Formula")],
                            [Cell(text="Water"), Cell(text="H2O")],
                        ],
                        header_rows=1,
                    ),
                    StatementsNode(
                        items=[
                            {"I": "Noble gases are inert."},
                            {"II": "Helium has two valence electrons."},
                        ]
                    ),
                    CodeNode(language="python", text="print('Chemistry')"),
                    BlankNode(index=1),
                    RawCropNode(figure_ref="crops/crop_q4.png", reason="complex formula"),
                    FigureNode(figure_ref="figures/fig1.png", caption={"en": "Apparatus diagram"}),
                ],
                options=[],
                source_pages=[2],
            ),
        ],
    )


class TestExporters:
    def test_registry(self):
        formats = list_exporters()
        assert "html" in formats
        assert "json" in formats
        assert "markdown" in formats
        assert "jsonl" in formats
        assert "qti" in formats

        exporter = get_exporter("markdown")
        assert isinstance(exporter, MarkdownExporter)

        with pytest.raises(KeyError):
            get_exporter("unsupported_xyz")

    def test_json_exporter(self, tmp_path: Path, sample_exam_document: ExamDocument):
        exporter = JSONExporter()
        out = tmp_path / "doc.json"
        res_path = exporter.export(sample_exam_document, out)
        assert res_path.exists()

        content = res_path.read_text(encoding="utf-8")
        roundtrip_doc = ExamDocument.model_validate_json(content)
        assert roundtrip_doc.schema_version == sample_exam_document.schema_version
        assert len(roundtrip_doc.questions) == len(sample_exam_document.questions)
        assert roundtrip_doc.metadata.exam_name == "National Entrance Examination"

    def test_markdown_exporter(self, tmp_path: Path, sample_exam_document: ExamDocument):
        exporter = MarkdownExporter()
        out = tmp_path / "exam.md"
        res_path = exporter.export(sample_exam_document, out)
        assert res_path.exists()

        md_text = res_path.read_text(encoding="utf-8")
        # Document title & metadata
        assert "# National Entrance Examination" in md_text
        assert "Physics & Chemistry" in md_text
        # Sections
        assert "## Section: Physics" in md_text
        assert "## Section: Chemistry" in md_text
        # Questions & Options
        assert "### Question 1" in md_text
        assert "What is the unit of force in SI?" in md_text
        assert "$F = m \\cdot a$" in md_text
        assert "- **(A)** Newton" in md_text
        assert "**Answer:** A" in md_text
        # Math display
        assert "$$" in md_text
        # Match columns & Table
        assert "| Column I | Column II |" in md_text
        assert "| Compound | Formula |" in md_text
        # Statements & Code & Blank
        assert "- **(I)** Noble gases are inert." in md_text
        assert "```python" in md_text
        assert "___(1)___" in md_text
        assert "![Apparatus diagram](figures/fig1.png)" in md_text

    def test_jsonl_exporter(self, tmp_path: Path, sample_exam_document: ExamDocument):
        exporter = JSONLExporter()
        out = tmp_path / "questions.jsonl"
        res_path = exporter.export(sample_exam_document, out)
        assert res_path.exists()

        lines = res_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == len(sample_exam_document.questions)

        # Parse each line as valid JSON
        for line in lines:
            data = json.loads(line)
            assert "id" in data
            assert "number" in data
            assert "kind" in data
            assert "stem" in data
            assert "options" in data
            assert "exam_metadata" in data
            assert data["exam_metadata"]["exam_name"] == "National Entrance Examination"

        # Check question 1 specifically
        q1_data = json.loads(lines[0])
        assert q1_data["number"] == 1
        assert q1_data["marks"]["positive"] == 4.0
        assert q1_data["answer"]["correct_options"] == ["A"]

    def test_qti_exporter(self, tmp_path: Path, sample_exam_document: ExamDocument):
        exporter = QTIExporter()
        out = tmp_path / "assessment.xml"
        res_path = exporter.export(sample_exam_document, out)
        assert res_path.exists()

        # XML parsing check
        tree = ET.parse(res_path)
        root = tree.getroot()
        assert "assessmentTest" in root.tag

        # Find items
        items = root.findall(".//{http://www.imsglobal.org/xsd/imsqti_v2p1}assessmentItem")
        # Questions 1, 2, 3 are supported; question 4 (MATCH) is unsupported
        assert len(items) == 3

        # Check sidecar report
        sidecar = tmp_path / "qti_unsupported.json"
        assert sidecar.exists()
        sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert sidecar_data["total_questions"] == 4
        assert sidecar_data["supported_count"] == 3
        assert sidecar_data["unsupported_count"] == 1
        assert sidecar_data["unsupported_questions"][0]["id"] == "q4"
        assert "match" in sidecar_data["unsupported_questions"][0]["kind"]

    def test_html_exporter(self, tmp_path: Path, sample_exam_document: ExamDocument):
        exporter = HTMLExporter()
        out = tmp_path / "exam.html"
        res_path = exporter.export(sample_exam_document, out, template_name="exam_v2.html.j2")
        assert res_path.exists()

        html_text = res_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html_text
        assert "Content-Security-Policy" in html_text
        assert "National Entrance Examination" in html_text
        assert "What is the unit of force in SI?" in html_text
        assert "Newton" in html_text

    def test_s9_package_integration_with_exporters(
        self, tmp_path: Path, sample_exam_document: ExamDocument
    ):
        cfg = ExamForgeConfig()
        cfg.set_flag("template_v2", True)
        cfg.set_flag("exporters", True)
        cfg.set_flag("include_answers", True)

        ctx = StageContext(
            document=sample_exam_document,
            config=cfg,
            spec=Spec.default(),
            stage_dir=tmp_path / "stage_s9",
            run_dir=tmp_path / "run",
        )

        stage = S9Package()
        res = stage.run(ctx)

        assert res.document is not None
        # Check generated artifacts
        assert (tmp_path / "run" / "output.html").exists()
        assert (tmp_path / "run" / "document.json").exists()
        assert (tmp_path / "run" / "output.md").exists()
        assert (tmp_path / "run" / "questions.jsonl").exists()
        assert (tmp_path / "run" / "qti.xml").exists()
        assert (tmp_path / "run" / "qti_unsupported.json").exists()

        # Check template_v2 CSS / classes in HTML
        html_content = (tmp_path / "run" / "output.html").read_text(encoding="utf-8")
        assert "exam-container" in html_content
        assert "options-container" in html_content
        assert "default-src 'none'" in html_content
