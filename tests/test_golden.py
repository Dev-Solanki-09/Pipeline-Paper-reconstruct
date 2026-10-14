"""Golden end-to-end integration test on real JEE Advanced exam paper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.orchestrator.runner import EXIT_NEEDS_REVIEW, EXIT_OK, EXIT_WARNINGS, PipelineRunner
from examforge.spec import Spec


class TestGoldenSuite:
    def test_golden_jee_exam_reconstruction(self, sample_pdf_path, tmp_path):
        """
        Execute full ExamForge pipeline on sample JEE Advanced paper
        and verify all core guarantees and output artifacts.
        """
        if sample_pdf_path is None or not sample_pdf_path.exists():
            pytest.skip("Sample JEE PDF not available in workspace")

        from examforge.cli import _build_stages

        # Run on first 6 pages for fast, deterministic CI execution
        config = ExamForgeConfig(
            paths={"runs": tmp_path / "runs", "ledger": tmp_path / "ledger", "cache": tmp_path / "cache"},
            max_pages=6,
        )
        spec = Spec.default()
        stages = _build_stages(config)

        runner = PipelineRunner(stages=stages, config=config, spec=spec)
        result = runner.execute(sample_pdf_path)

        # Pipeline execution should exit successfully or with review/warnings, never crash
        assert result.exit_code in (EXIT_OK, EXIT_WARNINGS, EXIT_NEEDS_REVIEW)
        assert result.document is not None

        # Verify Stage completion sequence
        manifest_path = result.run_dir / "manifest.json"
        assert manifest_path.exists()
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        completed_stages = [
            s["name"] for s in manifest_data.get("stages", []) if s.get("status") == "completed"
        ]
        expected_stages = [
            "s0_intake",
            "s3_parse",
            "s2_clean",
            "s4_structure",
            "s5_math",
            "s5_hindi",
            "s6_figures",
            "s8_verify",
            "s9_package",
        ]
        assert completed_stages == expected_stages

        # Verify Guarantee G2: No Silent Loss
        for block in result.document.blocks:
            if block.status.value == "dropped":
                assert block.drop_reason is not None and len(block.drop_reason) > 0

        # Verify Questions extracted
        assert len(result.document.questions) >= 5

        # Verify Output HTML
        html_path = result.run_dir / "output.html"
        assert html_path.exists()
        html_content = html_path.read_text(encoding="utf-8")

        # Verify unconstrained printing (no @page constraints)
        assert "@page" not in html_content
        assert "size: A4" not in html_content

        # Verify simple continuous dual-column 50/50 bilingual layout
        assert "col-50" in html_content
        assert "col-en" in html_content
        assert "col-hi" in html_content
        assert "question-row" in html_content
        assert "Q.1" in html_content or "1." in html_content
