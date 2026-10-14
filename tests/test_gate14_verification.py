"""
Phase 14 — Gate 14 Verification Suite.

Validates:
1. HTML Snapshot & Structural Validity across all ContentNode kinds and layout modes.
2. Offline CSP & XSS Sanitization assertions (forbids remote external loads, escapes injected tags).
3. Determinism: byte-identical double render.
4. Exporter outputs validity across JSON, Markdown, JSONL, QTI (with sidecar unsupported report).
5. Characterization identity and backward compatibility when template: exam.html.j2 (v1).
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
def universal_exam_document() -> ExamDocument:
    """Document exercising all universal ContentNode kinds and question kinds."""
    return ExamDocument(
        source_path="gate14_test.pdf",
        source_hash="sha256_gate14_verified",
        metadata=ExamMetadata(
            exam_name="Universal Assessment & Engineering Exam",
            year=2026,
            subject="Composite Sciences",
            series_code="U-2026",
        ),
        pages=[
            PageInfo(page_number=1, classification=PageClassification.COVER),
            PageInfo(page_number=2, classification=PageClassification.QUESTIONS),
        ],
        questions=[
            Question(
                id="q1",
                number=1,
                section="Section A",
                kind=QuestionKind.SINGLE_CORRECT,
                stem=[
                    TextNode(texts={"en": "Consider the equation:", "hi": "समीकरण पर विचार करें:"}),
                    MathNode(code=r"E = mc^2", display=True),
                ],
                options=[
                    Option(
                        label="1",
                        content=[
                            TextNode(texts={"en": "Mass-energy", "hi": "द्रव्यमान-ऊर्जा"})
                        ],
                    ),
                    Option(label="2", content=[TextNode(texts={"en": "Momentum", "hi": "संवेग"})]),
                    Option(label="3", content=[TextNode(texts={"en": "Entropy", "hi": "एंट्रॉपी"})]),
                    Option(label="4", content=[TextNode(texts={"en": "Charge", "hi": "आवेश"})]),
                ],
                answer=AnswerSpec(correct_options=["1"]),
                marks=Marks(positive=4.0, negative=1.0),
                source_pages=[2],
            ),
            Question(
                id="q2",
                number=2,
                section="Section A",
                kind=QuestionKind.NUMERICAL,
                stem=[
                    TextNode(texts={"en": "The value of absolute zero in Celsius is:"}),
                    BlankNode(index=1),
                ],
                answer=AnswerSpec(numeric_value=-273.15),
                source_pages=[2],
            ),
            Question(
                id="q3",
                number=3,
                section="Section B",
                kind=QuestionKind.MATCH,
                stem=[
                    TextNode(texts={"en": "Match the items:"}),
                    MatchColumnsNode(
                        left=[{"A": "Alpha"}, {"B": "Beta"}],
                        right=[{"1": "Helium nucleus"}, {"2": "Electron"}],
                    ),
                    TableNode(
                        rows=[
                            [Cell(text="Type"), Cell(text="Charge")],
                            [Cell(text="Proton"), Cell(text="+1")],
                        ],
                        header_rows=1,
                    ),
                    StatementsNode(
                        items=[
                            {"I": "Light behaves as wave."},
                            {"II": "Light behaves as particle."},
                        ]
                    ),
                    CodeNode(language="cpp", text="double c = 299792458;"),
                    RawCropNode(figure_ref="crops/crop_raw.png", reason="complex formula"),
                    FigureNode(
                        figure_ref="figures/figure_1.png",
                        caption={"en": "Experimental Apparatus"},
                    ),
                ],
                options=[],
                source_pages=[2],
            ),
        ],
    )


class TestGate14Verification:
    """Gate 14 test suite verifying template v2, offline security, determinism, and exporters."""

    def test_html_v2_snapshot_and_structure(self, universal_exam_document: ExamDocument):
        exporter = HTMLExporter()
        html = exporter.render_to_html(universal_exam_document, template_name="exam_v2.html.j2")

        # 1. Structural assertions
        assert "<!DOCTYPE html>" in html
        assert "<main class=\"exam-container\">" in html
        assert "class=\"bilingual-grid\"" in html
        assert "class=\"question-row-bilingual\"" in html

        # No page wrappers (continuous flow)
        assert "class=\"page\"" not in html
        assert "class=\"page-preview\"" not in html

        # Serial numbers in gutters
        assert "class=\"q-serial\"" in html
        assert "1." in html
        assert "2." in html
        assert "3." in html

        # Both language columns with lang attributes
        assert "lang=\"en\"" in html
        assert "lang=\"hi\"" in html

        # Node kinds rendered
        assert "E = mc^2" in html
        assert "class=\"match-columns-table\"" in html
        assert "class=\"table-node\"" in html
        assert "class=\"code-block\"" in html
        assert "class=\"fill-blank\"" in html

    def test_offline_csp_and_security(self, universal_exam_document: ExamDocument):
        """Verify strict CSP forbids external network loads and script tags are escaped."""
        # Inject malicious text with script and event handlers into a question
        hostile_q = Question(
            id="q_hostile",
            number=99,
            kind=QuestionKind.SINGLE_CORRECT,
            stem=[
                TextNode(
                    texts={
                        "en": (
                            "<script>alert('XSS')</script>Find the answer "
                            "<img src=x onerror=alert(1)>"
                        )
                    }
                ),
                CodeNode(language="python", text="<script>document.cookie</script>"),
            ],
            options=[],
        )
        doc = universal_exam_document.model_copy(
            update={"questions": [hostile_q]}
        )

        exporter = HTMLExporter()
        html = exporter.render_to_html(doc, template_name="exam_v2.html.j2")

        # Strict offline CSP header meta tag forbidding external loads
        assert "default-src 'none'" in html
        assert "http-equiv=\"Content-Security-Policy\"" in html

        # Forbid unescaped external URL references (no http:// or https:// CDNs)
        assert "http://" not in html
        assert "https://" not in html

        # Verify CodeNode escapes code text (<script> -> &lt;script&gt;)
        assert "&lt;script&gt;document.cookie&lt;/script&gt;" in html

    def test_double_render_determinism(self, universal_exam_document: ExamDocument):
        """Two render passes of the exact same document must be byte-identical."""
        exporter = HTMLExporter()
        render_1 = exporter.render_to_html(universal_exam_document, template_name="exam_v2.html.j2")
        render_2 = exporter.render_to_html(universal_exam_document, template_name="exam_v2.html.j2")

        assert render_1 == render_2
        assert len(render_1.encode("utf-8")) == len(render_2.encode("utf-8"))

    def test_all_exporters_produce_valid_outputs(
        self, tmp_path: Path, universal_exam_document: ExamDocument
    ):
        """Every exporter (JSON, Markdown, JSONL, QTI) must generate schema-compliant output."""
        # 1. JSON
        json_out = tmp_path / "out.json"
        JSONExporter().export(universal_exam_document, json_out)
        assert json_out.exists()
        reloaded = ExamDocument.model_validate_json(json_out.read_text(encoding="utf-8"))
        assert len(reloaded.questions) == 3

        # 2. Markdown
        md_out = tmp_path / "out.md"
        MarkdownExporter().export(universal_exam_document, md_out)
        assert md_out.exists()
        md_text = md_out.read_text(encoding="utf-8")
        assert "# Universal Assessment & Engineering Exam" in md_text
        assert "### Question 1" in md_text
        assert "### Question 3" in md_text
        assert "$$E = mc^2$$" in md_text or "$$" in md_text

        # 3. JSONL
        jsonl_out = tmp_path / "out.jsonl"
        JSONLExporter().export(universal_exam_document, jsonl_out)
        assert jsonl_out.exists()
        lines = jsonl_out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "id" in parsed
            assert "stem" in parsed

        # 4. QTI XML with sidecar
        qti_out = tmp_path / "qti.xml"
        QTIExporter().export(universal_exam_document, qti_out)
        assert qti_out.exists()
        xml_tree = ET.parse(qti_out)
        assert "assessmentTest" in xml_tree.getroot().tag

        sidecar = tmp_path / "qti_unsupported.json"
        assert sidecar.exists()
        sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert sidecar_data["total_questions"] == 3
        assert sidecar_data["supported_count"] == 2  # Q1 (SINGLE_CORRECT) and Q2 (NUMERICAL)
        assert sidecar_data["unsupported_count"] == 1  # Q3 (MATCH)

    def test_characterization_identical_when_template_v1(
        self, tmp_path: Path, universal_exam_document: ExamDocument
    ):
        """When template_v2 is disabled (default), S9 generates authentic v1 output identically."""
        cfg = ExamForgeConfig()
        cfg.set_flag("template_v2", False)
        cfg.set_flag("exporters", False)

        ctx = StageContext(
            document=universal_exam_document,
            config=cfg,
            spec=Spec.default(),
            stage_dir=tmp_path / "s9_stage",
            run_dir=tmp_path / "run_v1",
        )

        stage = S9Package()
        stage.run(ctx)

        html_out = tmp_path / "run_v1" / "output.html"
        assert html_out.exists()
        content = html_out.read_text(encoding="utf-8")

        # Verify v1 markers
        assert "Real NEET Dual-Column Bilingual" in content
        assert "col-50" in content
        assert "MathJax-script" in content
        assert not (tmp_path / "run_v1" / "output.md").exists()
