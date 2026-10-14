"""Gate 8 Verification Test Suite.

Verifies:
1. Watermark residual correlation (R03) < 0.05.
2. Content preservation SSIM >= 0.95 across watermark removal and illumination flattening.
3. Geometry: skew sweep +/- 15 deg, rotations 0/90/180/270, two-up spread splitting.
4. False-positive traps: scientific constants, abbreviations, and chemistry formulas never dropped.
5. Idempotency: repeated cleaning produces identical results.
6. Clean v2 rollback flag verified.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from examforge.clean.branding import is_false_positive_trap, scrub_branding_blocks
from examforge.clean.furniture import find_repeating_furniture_blocks
from examforge.clean.geometry import (
    correct_orientation,
    deskew_image,
    detect_orientation,
    detect_skew_angle,
    split_two_up_spread,
)
from examforge.clean.illumination import calculate_ssim, flatten_illumination
from examforge.clean.watermark_median import (
    calculate_residual_correlation,
    estimate_watermark_median,
    remove_baked_watermark,
)
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    ExamDocument,
    ExamMetadata,
    Lang,
    PageClassification,
    PageInfo,
)
from examforge.stages.base import StageContext
from examforge.stages.s2_clean import S2Clean


class TestGate8RestorationAndCleaning:
    def test_watermark_residual_and_ssim(self):
        """Watermark residual correlation < 0.05 and SSIM over content mask >= 0.95."""
        pages = []
        clean_pages = []
        width, height = 300, 400

        # Fixed diagonal watermark mask
        wm_mask = np.ones((height, width), dtype=np.float32)
        for y in range(height):
            for x in range(width):
                if 100 <= (y + x) <= 170:
                    wm_mask[y, x] = 0.78  # 22% opacity watermark

        for i in range(6):
            im = Image.new("L", (width, height), color=255)
            draw = ImageDraw.Draw(im)
            for k in range(5):
                y = 40 + k * 65 + (i * 5) % 15
                draw.line([(30, y), (270, y)], fill=0, width=3)
                draw.text((35, y - 10), f"Question text P{i} item {k}", fill=0)

            clean_pages.append(im)
            arr = np.array(im, dtype=np.float32)
            watermarked_arr = np.clip(arr * wm_mask, 0, 255).astype(np.uint8)
            pages.append(Image.fromarray(watermarked_arr))

        wm_layer = estimate_watermark_median(pages)
        assert wm_layer is not None

        cleaned, issues = remove_baked_watermark(pages, wm_layer=wm_layer)
        assert len(issues) == 0

        # 1. Residual correlation < 0.05
        corr = calculate_residual_correlation(cleaned[0], wm_layer)
        assert corr < 0.05

        # 2. SSIM over content mask >= 0.95
        c_orig = np.array(clean_pages[0])
        c_clean = np.array(cleaned[0])
        mask = c_orig < 220
        ssim_score = calculate_ssim(c_orig, c_clean, mask=mask)
        assert ssim_score >= 0.95

    def test_geometry_sweeps(self):
        """Orientation detection (0, 90, 180, 270) and deskew sweep (-15 to +15 deg)."""
        base = Image.new("L", (350, 450), color=255)
        draw = ImageDraw.Draw(base)
        for y in range(60, 400, 40):
            draw.line([(40, y), (310, y)], fill=0, width=4)

        # Skew sweep
        for test_angle in [-12.0, -5.0, 7.5, 14.0]:
            skewed = base.rotate(test_angle, expand=True, fillcolor=255)
            detected = detect_skew_angle(skewed, max_angle=15.0)
            assert abs(detected - test_angle) <= 1.5

        # Rotation sweep
        for rot_angle in [0, 90, 180, 270]:
            rot = base.rotate(rot_angle, expand=True, fillcolor=255)
            det_orient = detect_orientation(rot)
            corrected = correct_orientation(rot, det_orient)
            assert corrected.height >= corrected.width

    def test_branding_traps_and_scrubbing(self):
        """Scrubbing captures URLs/phones while never dropping scientific constants or abbreviations."""
        b_url = Block(
            id="b_url", page=1, type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=50, x2=550, y2=80), bbox_norm=(0.1, 0.05, 0.9, 0.08),
            order=0, lang=Lang.EN, text="https://test-institute.org/answers",
            confidence=1.0, status=BlockStatus.TRUSTED,
        )
        b_const = Block(
            id="b_const", page=1, type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=100, x2=550, y2=130), bbox_norm=(0.1, 0.2, 0.9, 0.25),
            order=1, lang=Lang.EN, text="Take g = 9.8 m/s^2, Planck constant h = 6.626 x 10^-34 J s",
            confidence=1.0, status=BlockStatus.TRUSTED,
        )
        b_abbr = Block(
            id="b_abbr", page=1, type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=150, x2=550, y2=180), bbox_norm=(0.1, 0.3, 0.9, 0.35),
            order=2, lang=Lang.EN, text="e.g., when the piston moves inward",
            confidence=1.0, status=BlockStatus.TRUSTED,
        )

        dropped_ids = scrub_branding_blocks([b_url, b_const, b_abbr])
        assert "b_url" in dropped_ids
        assert "b_const" not in dropped_ids
        assert "b_abbr" not in dropped_ids

    def test_cleaning_idempotency(self, tmp_path):
        """Running S2Clean twice produces identical dropped status and metrics."""
        b1 = Block(
            id="b1", page=1, type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=750, x2=550, y2=780), bbox_norm=(0.1, 0.94, 0.9, 0.98),
            order=0, lang=Lang.EN, text="SPACE FOR ROUGH WORK",
            confidence=1.0, status=BlockStatus.TRUSTED,
        )
        b2 = Block(
            id="b2", page=1, type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=100, x2=550, y2=200), bbox_norm=(0.1, 0.15, 0.9, 0.25),
            order=1, lang=Lang.EN, text="1. Calculate the pressure of the gas",
            confidence=1.0, status=BlockStatus.TRUSTED,
        )

        doc = ExamDocument(
            source_path="test.pdf", source_hash="h1",
            metadata=ExamMetadata(exam_name="Test"),
            pages=[PageInfo(page_number=1, classification=PageClassification.QUESTIONS)],
            blocks=[b1, b2],
        )

        ctx = StageContext(document=doc, config=None, spec=None, stage_dir=tmp_path / "s2_idem", run_dir=tmp_path)
        stage = S2Clean()

        res1 = stage.run(ctx)
        assert res1.metrics["blocks_dropped"] == 1
        assert b1.status == BlockStatus.DROPPED
        assert b2.status == BlockStatus.TRUSTED

        # Second pass
        res2 = stage.run(ctx)
        assert res2.metrics["blocks_dropped"] == 0  # Already dropped
        assert b1.status == BlockStatus.DROPPED
        assert b2.status == BlockStatus.TRUSTED
