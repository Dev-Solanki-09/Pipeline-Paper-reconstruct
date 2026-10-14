"""Tests for Profile CLI and Stage S1 Profile."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from examforge.cli import main
from examforge.config import ExamForgeConfig
from examforge.ir.schema import BBox, Block, ExamDocument, PageClassification, PageInfo
from examforge.stages.base import StageContext
from examforge.stages.s1_profile import S1Profile


def test_cli_profile_help():
    runner = CliRunner()
    res = runner.invoke(main, ["profile", "--help"])
    assert res.exit_code == 0
    assert "scaffold" in res.output


def test_cli_profile_scaffold_help():
    runner = CliRunner()
    res = runner.invoke(main, ["profile", "scaffold", "--help"])
    assert res.exit_code == 0
    assert "--output" in res.output
    assert "--id" in res.output


def test_s1_profile_stage_default_passthrough(tmp_path: Path):
    stage = S1Profile()
    cfg = ExamForgeConfig()  # autoprofile is False by default

    doc = ExamDocument(
        source_path="mock.pdf",
        pages=[PageInfo(page_number=1, width_px=600, height_px=800)],
        blocks=[Block(id="b1", page=1, bbox=BBox(x1=10, y1=10, x2=100, y2=20), text="Sample")],
    )
    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s1",
        run_dir=tmp_path / "run",
    )

    res = stage.run(ctx)
    assert not res.metrics["autoprofiled"]
    assert res.metrics["profile"] == "neet_ug"


def test_s1_profile_stage_autoprofile_enabled(tmp_path: Path):
    stage = S1Profile()
    cfg = ExamForgeConfig()
    cfg.flags["autoprofile"] = True
    cfg.profile_cache_path = tmp_path / "cache.sqlite"

    doc = ExamDocument(
        source_path="mock.pdf",
        pages=[
            PageInfo(
                page_number=1,
                width_px=600,
                height_px=800,
                classification=PageClassification.QUESTIONS,
            )
        ],
        blocks=[
            Block(
                id="b1",
                page=1,
                bbox=BBox(x1=50, y1=100, x2=550, y2=130),
                text="1. Calculate force.",
            ),
            Block(
                id="b2", page=1, bbox=BBox(x1=50, y1=135, x2=550, y2=165), text="(1) 10 N (2) 20 N"
            ),
        ],
    )
    ctx = StageContext(
        document=doc,
        spec=None,
        config=cfg,
        stage_dir=tmp_path / "s1",
        run_dir=tmp_path / "run",
    )

    # First run: cache miss -> inferred
    res1 = stage.run(ctx)
    assert res1.metrics["autoprofiled"]
    assert not res1.metrics["cache_hit"]
    assert "auto_" in res1.metrics["profile"]

    # Second run with same fingerprint: cache hit!
    res2 = stage.run(ctx)
    assert res2.metrics["autoprofiled"]
    assert res2.metrics["cache_hit"]
    assert res2.metrics["profile"] == res1.metrics["profile"]
