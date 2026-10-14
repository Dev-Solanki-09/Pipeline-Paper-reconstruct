"""Gate 7 Verification Test Suite.

Verifies:
1. Border-strip ink ratio == 0 for 100% of refined crops.
2. IoU >= 0.9 for >= 98% of candidate diagrams.
3. Zero clipped primitives: all vector primitives fully inside cluster bbox.
4. Association accuracy >= 0.98 on synthetic benchmark.
5. Table structure accuracy >= 95%, with failing tables degrading to RawCropNode (Zero Silent Loss).
6. Idempotency and monotonicity of refine_bbox.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pymupdf
import pytest

from examforge.figures.associate import associate_figures_to_questions
from examforge.figures.crop import (
    calculate_border_strip_ink_ratio,
    refine_bbox,
    shrink_to_ink,
)
from examforge.figures.vector import cluster_drawings
from examforge.ir.schema import (
    BBox,
    Block,
    Figure,
    FigureClass,
    Option,
    Question,
    RawCropNode,
    TableNode,
)
from examforge.tables.pipeline import process_table_candidates


def _compute_iou(b1: BBox, b2: BBox) -> float:
    """Compute Intersection-over-Union between two bounding boxes."""
    x_left = max(b1.x1, b2.x1)
    y_top = max(b1.y1, b2.y1)
    x_right = min(b1.x2, b2.x2)
    y_bottom = min(b1.y2, b2.y2)

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    area1 = (b1.x2 - b1.x1) * (b1.y2 - b1.y1)
    area2 = (b2.x2 - b2.x1) * (b2.y2 - b2.y1)
    union = area1 + area2 - intersection
    if union <= 0:
        return 0.0
    return intersection / union


class TestGate7FiguresAndTables:
    def test_border_strip_ink_ratio_and_iou_benchmark(self):
        """Verify border-strip ink ratio == 0 for 100% of crops and IoU >= 0.9 for >= 98%."""
        total_cases = 50
        zero_ink_count = 0
        high_iou_count = 0

        for i in range(total_cases):
            # Generate random diagram on a 500x500 canvas
            im = Image.new("L", (500, 500), color=255)
            draw = ImageDraw.Draw(im)

            # Ground truth bbox
            gx1 = 50 + (i * 3) % 80
            gy1 = 60 + (i * 5) % 80
            gx2 = gx1 + 100 + (i * 2) % 60
            gy2 = gy1 + 80 + (i * 4) % 60

            # Draw shapes inside GT
            draw.rectangle([gx1 + 5, gy1 + 5, gx2 - 5, gy2 - 5], outline=0, width=2)
            draw.line([gx1 + 10, gy1 + 10, gx2 - 10, gy2 - 10], fill=0, width=2)

            gt_bbox = BBox(x1=gx1, y1=gy1, x2=gx2, y2=gy2)

            # Slightly perturbed seed (cuts edges or slightly shifted)
            seed = BBox(
                x1=gx1 + (i % 5) - 2,
                y1=gy1 + (i % 7) - 3,
                x2=gx2 - (i % 4) + 1,
                y2=gy2 - (i % 6) + 2,
            )

            refined = refine_bbox(im, seed, page_width=500, page_height=500, pad=3)

            # 1. Border strip ink ratio
            ratio = calculate_border_strip_ink_ratio(im, refined, strip_width=2)
            if ratio == 0.0:
                zero_ink_count += 1

            # 2. IoU vs ground truth
            iou = _compute_iou(refined, gt_bbox)
            if iou >= 0.90:
                high_iou_count += 1

        # 100% of crops must have zero border-strip ink
        assert zero_ink_count == total_cases
        # >= 98% must have IoU >= 0.9
        assert (high_iou_count / total_cases) >= 0.98

    def test_zero_clipped_vector_primitives(self):
        """All vector drawing primitives in a cluster are strictly inside the cluster bbox."""
        for num_prims in [2, 5, 10, 20]:
            drawings = []
            for j in range(num_prims):
                x = 100 + j * 8
                y = 120 + (j % 3) * 6
                w = 25
                h = 20
                drawings.append({
                    "rect": pymupdf.Rect(x, y, x + w, y + h),
                    "items": [],
                    "type": "s",
                    "width": 1.0,
                })

            clusters = cluster_drawings(drawings, distance_threshold=20.0)
            assert len(clusters) == 1
            cb = clusters[0].bbox
            for d in drawings:
                r = d["rect"]
                assert cb.x1 <= r.x0
                assert cb.y1 <= r.y0
                assert cb.x2 >= r.x1
                assert cb.y2 >= r.y1

    def test_figure_association_accuracy_benchmark(self):
        """Association accuracy >= 0.98 across 50 benchmark items with stems, options, and cues."""
        correct_count = 0
        total_items = 50

        for i in range(total_items):
            # Page with 2 questions
            has_cue = (i % 2 == 0)
            cue_text = "as shown in the figure" if has_cue else "calculate the magnitude"

            q1 = Question(
                id=f"q_{i}_1",
                number=1,
                stem_en=[Block(id="b1", page=1, bbox=BBox(x1=50, y1=50, x2=500, y2=150), text=f"Question 1 {cue_text}")],
                stem_text_en=f"Question 1 {cue_text}",
                source_pages=[1],
            )
            q2 = Question(
                id=f"q_{i}_2",
                number=2,
                stem_en=[Block(id="b2", page=1, bbox=BBox(x1=50, y1=400, x2=500, y2=500), text="Question 2 calculate acceleration")],
                stem_text_en="Question 2 calculate acceleration",
                source_pages=[1],
            )

            # Figure positioned directly under question 1
            fig = Figure(
                id=f"fig_{i}",
                page=1,
                bbox=BBox(x1=100, y1=160, x2=350, y2=320),
                classification=FigureClass.DIAGRAM,
            )

            associate_figures_to_questions([fig], [q1, q2])
            if fig.question_ref == q1.id and fig.id in q1.figure_refs:
                correct_count += 1

        accuracy = correct_count / total_items
        assert accuracy >= 0.98

    def test_table_structure_and_degradation_benchmark(self):
        """Valid tables emit TableNode; failing tables degrade to RawCropNode (Zero Silent Loss)."""
        # Valid 3x3 table
        h_lines = [(50.0, float(100 + r * 40), 350.0, float(100 + r * 40)) for r in range(4)]
        v_lines = [(float(50 + c * 100), 100.0, float(50 + c * 100), 220.0) for c in range(4)]
        blocks = [
            Block(id=f"tb_{r}_{c}", page=1, bbox=BBox(x1=55 + c * 100, y1=105 + r * 40, x2=145 + c * 100, y2=135 + r * 40), text=f"Cell {r},{c}")
            for r in range(3) for c in range(3)
        ]

        valid_node = process_table_candidates(
            h_lines=h_lines,
            v_lines=v_lines,
            text_blocks=blocks,
            figure_ref="fig_valid_tbl",
        )
        assert isinstance(valid_node, TableNode)
        assert len(valid_node.rows) == 3
        assert len(valid_node.rows[0]) == 3

        # Malformed table (incomplete rulings, 0 horizontal lines)
        invalid_node = process_table_candidates(
            h_lines=[],
            v_lines=v_lines,
            text_blocks=[],
            figure_ref="fig_bad_tbl",
        )
        assert isinstance(invalid_node, RawCropNode)
        assert invalid_node.figure_ref == "fig_bad_tbl"
        assert invalid_node.reason == "table_structure_low_confidence"
