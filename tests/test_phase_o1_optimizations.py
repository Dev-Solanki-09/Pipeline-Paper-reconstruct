"""Tests for Phase O1: Zero-behavior-change quick wins."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from examforge.config import ExamForgeConfig
from examforge.engines.paddle_vl import PaddleVLAdapter, PaddleVLConfig
from examforge.figures.vector import cluster_drawings
import pymupdf
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    PageClassification,
    PageInfo,
)
from examforge.orchestrator.manifest import Manifest
from examforge.orchestrator.runner import PipelineRunner, RunDirectory
from examforge.profiles.compute import calculate_thread_budget
from examforge.profiles.loader import ProfileLoadError, _vet_profile_regexes
from examforge.profiles.schema import ExamProfile, NumberingProfileConfig
from examforge.raster_cache import get_cached_pixmap, reset_pixmap_cache
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult


class TestO1WarmEngines:
    def test_model_init_count_is_one_across_multiple_adapters(self):
        PaddleVLAdapter.reset_shared_instances()
        assert PaddleVLAdapter.get_model_init_count() == 0

        # Simulate local library present with standard PaddleOCR
        mock_paddle = MagicMock(spec=["PaddleOCR"])
        mock_instance = MagicMock()
        mock_instance.ocr.return_value = [
            [[[[0, 0], [100, 0], [100, 20], [0, 20]], ("Question 1", 0.99)]]
        ]
        mock_paddle.PaddleOCR.return_value = mock_instance

        with patch("importlib.import_module", return_value=mock_paddle):
            dummy_img = Path("tests/dummy.png")
            dummy_img.touch(exist_ok=True)
            try:
                # First adapter call initializes model
                adapter1 = PaddleVLAdapter()
                blocks1 = adapter1._call_local_library(dummy_img, 1)
                assert len(blocks1) == 1
                assert PaddleVLAdapter.get_model_init_count() == 1

                # Second adapter call reuses same warmed model
                adapter2 = PaddleVLAdapter()
                blocks2 = adapter2._call_local_library(dummy_img, 2)
                assert len(blocks2) == 1
                assert PaddleVLAdapter.get_model_init_count() == 1
            finally:
                if dummy_img.exists():
                    dummy_img.unlink()
                PaddleVLAdapter.reset_shared_instances()


class TestO1ThreadBudget:
    def test_budget_enforces_workers_times_threads_le_cpus(self):
        workers, threads = calculate_thread_budget(cpu_count=8, ram_gb=16.0, tier="standard")
        assert workers * threads <= 8
        assert workers >= 1
        assert threads >= 1

    def test_lite_tier_uses_single_worker(self):
        workers, threads = calculate_thread_budget(cpu_count=16, ram_gb=32.0, tier="lite")
        assert workers == 1
        assert threads == 16


class TestO1RenderOnceCache:
    def test_render_once_pixmap_caching(self):
        reset_pixmap_cache()
        mock_pix = MagicMock()
        mock_pix.samples = b"\x00" * (100 * 100)
        mock_pix.width = 100
        mock_pix.height = 100
        mock_pix.alpha = False

        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix

        # Call twice with same params
        arr1 = get_cached_pixmap(mock_page, "hash_123", dpi=150, grayscale=True)
        arr2 = get_cached_pixmap(mock_page, "hash_123", dpi=150, grayscale=True)

        assert mock_page.get_pixmap.call_count == 1
        assert arr1.dtype == np.uint8
        assert np.array_equal(arr1, arr2)
        reset_pixmap_cache()


class TestO1SpatialClustering:
    def test_spatial_clustering_matches_ground_truth(self):
        d1 = {"rect": pymupdf.Rect(10.0, 10.0, 20.0, 20.0)}
        d2 = {"rect": pymupdf.Rect(15.0, 15.0, 25.0, 25.0)}  # close/overlapping with d1
        d3 = {"rect": pymupdf.Rect(200.0, 200.0, 210.0, 210.0)}  # far away
        clusters = cluster_drawings([d1, d2, d3], distance_threshold=20.0)
        assert len(clusters) == 2
        # One cluster contains d1 and d2
        c0 = next(c for c in clusters if d1 in c.drawings)
        assert d2 in c0.drawings
        assert d3 not in c0.drawings


class DummyStage(Stage):
    name = "dummy_minor"

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult(document=ctx.document)


class TestO1Checkpoints:
    def test_checkpoint_tiers(self, tmp_path):
        run_dir = RunDirectory(tmp_path, "run_test_cp")
        run_dir.create()
        doc = ExamDocument(source_path="test.pdf", source_hash="h1")

        # Tier 'major' skips minor stage checkpoints but writes root
        run_dir.save_document(doc, stage_name="s4_structure", tier="major")
        assert not run_dir.stage_checkpoint("s4_structure").exists()
        assert run_dir.document_path.exists()

        # Major stage is saved
        run_dir.save_document(doc, stage_name="s3_parse", tier="major")
        assert run_dir.stage_checkpoint("s3_parse").exists()


class TestO1RegexHygiene:
    def test_catastrophic_nested_quantifier_rejected(self):
        profile = ExamProfile(
            id="bad_regex_prof",
            name="Bad Regex Profile",
            numbering=NumberingProfileConfig(patterns=[r"^(a+)+$"]),
        )
        with pytest.raises(ProfileLoadError, match="Catastrophic ReDoS"):
            _vet_profile_regexes(profile, "bad_regex_prof")

    def test_safe_regex_accepted(self):
        profile = ExamProfile(
            id="safe_prof",
            name="Safe Profile",
            numbering=NumberingProfileConfig(patterns=[r"^\(?\d+\)?[.:]"]),
        )
        _vet_profile_regexes(profile, "safe_prof")  # should not raise
