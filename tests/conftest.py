"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.config import ExamForgeConfig
from examforge.ir.schema import ExamDocument, ExamMetadata
from examforge.spec import Spec


@pytest.fixture
def tmp_runs(tmp_path: Path) -> Path:
    """Temporary runs directory."""
    runs = tmp_path / "runs"
    runs.mkdir()
    return runs


@pytest.fixture
def default_config(tmp_runs: Path) -> ExamForgeConfig:
    """Config pointing at temp directories."""
    return ExamForgeConfig(
        paths={"runs": tmp_runs, "ledger": tmp_runs / "ledger", "cache": tmp_runs / ".cache"},
    )


@pytest.fixture
def default_spec() -> Spec:
    """Default spec with all standard rules."""
    return Spec.default()


@pytest.fixture
def empty_document(tmp_path: Path) -> ExamDocument:
    """An ExamDocument with no pages or content."""
    return ExamDocument(
        source_path=str(tmp_path / "test.pdf"),
        source_hash="abc123",
        metadata=ExamMetadata(exam_name="Test Exam", year=2025),
    )


@pytest.fixture
def sample_pdf_path() -> Path | None:
    """
    Path to the sample JEE Advanced PDF, if available.

    Returns None if the file is not present (tests that need it
    should skip with pytest.mark.skipif).
    """
    candidates = [
        Path(r"c:\Users\D.Solanki\pipeline\JEE ADV  MT # 4 NURTURE SANKALP -I BATCH PAPER D-27-07-2025.pdf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None
