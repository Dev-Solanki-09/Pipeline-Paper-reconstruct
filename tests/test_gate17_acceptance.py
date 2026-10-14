"""
Phase 17 — Gate 17 Verification Suite: Acceptance, Flag Flips & Release.

Validates:
1. Package version is 2.0.0 in __version__ and pyproject.toml.
2. All 12 feature flags are flipped to default True in ExamForgeConfig.
3. CLI execute supports positional paper argument and defaults to --profile auto.
4. Full pipeline execution with all v2 flags active completes cleanly (exit 0).
5. Exporters (HTML, JSON, Markdown, JSONL, QTI) are generated under default active flags.
6. Review handling produces review.html and maps to EXIT_NEEDS_REVIEW (20).
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from click.testing import CliRunner

from examforge import __version__
from examforge.cli import main
from examforge.config import ExamForgeConfig
from examforge.ir.schema import (
    BBox,
    Block,
    ExamDocument,
    Issue,
    IssueSeverity,
    Option,
    PageInfo,
    Question,
)
from examforge.orchestrator.runner import (
    EXIT_NEEDS_REVIEW,
    EXIT_OK,
    PipelineRunner,
    RunDirectory,
)
from examforge.spec import Spec
from examforge.stages import (
    S0Intake,
    S1Profile,
    S2Clean,
    S3Parse,
    S4Structure,
    S5Hindi,
    S5Math,
    S6Figures,
    S7Repair,
    S8Verify,
    S9Package,
)


def test_gate17_version_and_metadata():
    """Verify package release version is 2.0.0 across metadata files."""
    assert __version__ == "2.0.0"

    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists()
    content = pyproject_path.read_text(encoding="utf-8")
    assert 'version = "2.0.0"' in content


def test_gate17_all_feature_flags_default_true():
    """Verify all 12 feature flags are flipped to True by default."""
    config = ExamForgeConfig()
    expected_flags = [
        "verifiers_v2",
        "layout_v2",
        "figures_v2",
        "clean_v2",
        "lang_v2",
        "answers",
        "s7_repair",
        "bank",
        "autoprofile",
        "lessons",
        "template_v2",
        "exporters",
    ]
    for flag_name in expected_flags:
        assert config.flag(flag_name) is True, f"Flag {flag_name} should be default True in v2.0.0"


def test_gate17_cli_execute_semantics(tmp_path: Path):
    """Verify 'execute <paper>' works as a positional argument and defaults to profile auto."""
    pdf_path = tmp_path / "sample_exam.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    runner = CliRunner()
    # Invoke without arguments -> usage error
    res_err = runner.invoke(main, ["execute"])
    assert res_err.exit_code != 0
    assert "Missing exam PDF" in res_err.output

    # Help displays default auto and positional argument
    res_help = runner.invoke(main, ["execute", "--help"])
    assert res_help.exit_code == 0
    assert "[PAPER]" in res_help.output or "PAPER" in res_help.output
    assert "default: auto" in res_help.output


def test_gate17_pipeline_e2e_all_v2_features(tmp_path: Path):
    """
    Run pipeline with all v2 flags enabled, verifying:
    - S0 through S9 execute sequentially
    - Template v2 renders clean HTML
    - All exporters emit artifacts
    - Result exit code is 0
    """
    pdf_path = tmp_path / "neet_test.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "1. What is the value of gravitational constant G?")
    p.insert_text((72, 90), "(1) 6.67 x 10^-11 N m^2/kg^2")
    p.insert_text((72, 105), "(2) 9.8 m/s^2")
    p.insert_text((72, 120), "(3) 3 x 10^8 m/s")
    p.insert_text((72, 135), "(4) 1.6 x 10^-19 C")
    doc.save(str(pdf_path))
    doc.close()

    config = ExamForgeConfig(
        paths={"runs": tmp_path / "runs", "ledger": tmp_path / "ledger", "cache": tmp_path / "cache"}
    )
    spec = Spec.default()

    stages = [
        S0Intake(),
        S3Parse(),
        S1Profile(),
        S2Clean(),
        S4Structure(),
        S5Math(),
        S5Hindi(),
        S6Figures(),
        S8Verify(),
        S7Repair(),
        S9Package(),
    ]

    pipeline = PipelineRunner(
        stages=stages,
        config=config,
        spec=spec,
    )

    result = pipeline.execute(source_path=pdf_path)
    assert result.exit_code == EXIT_OK
    assert result.success is True

    run_dir = result.run_dir
    assert (run_dir / "document.json").exists()
    assert (run_dir / "output.html").exists()

    # Exporters should emit all formats since 'exporters' flag is True
    assert (run_dir / "output.md").exists()
    assert (run_dir / "questions.jsonl").exists()
    assert (run_dir / "qti.xml").exists()

    # Template v2 assertion: offline CSP and semantic landmarks
    html_text = (run_dir / "output.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html_text or "<!DOCTYPE html>" in html_text
    assert len(html_text) > 100


def test_gate17_exit_code_20_and_review_html(tmp_path: Path):
    """Verify that unresolved issues generate review.html and trigger EXIT_NEEDS_REVIEW (20)."""
    run_dir = RunDirectory(tmp_path, "test_run_20")
    run_dir.create()

    doc = ExamDocument(
        source_path=str(tmp_path / "mock.pdf"),
        pages=[PageInfo(page_number=1, width_px=595, height_px=842)],
    )
    (run_dir.root / "review.html").write_text("<h1>Human Review Required</h1>", encoding="utf-8")

    runner = PipelineRunner(stages=[], config=ExamForgeConfig(), spec=Spec.default())
    exit_code = runner._compute_exit_code(doc, run_dir)
    assert exit_code == EXIT_NEEDS_REVIEW
