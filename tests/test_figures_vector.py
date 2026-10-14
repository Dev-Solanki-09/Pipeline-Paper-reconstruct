"""Tests for vector figure extraction (PyMuPDF get_drawings clustering and filtering)."""

from __future__ import annotations

from pathlib import Path
import pymupdf

import pytest

from examforge.figures.vector import (
    VectorCluster,
    cluster_drawings,
    compute_path_signature,
    extract_vector_figures,
    find_repeated_vector_signatures,
    is_separator_rule,
)
from examforge.ir.schema import BBox, FigureClass


class TestVectorDrawingClustering:
    def test_cluster_nearby_primitives(self):
        """Two primitives close to each other should be in the same cluster."""
        # Create drawings with rects
        d1 = {
            "rect": pymupdf.Rect(100, 100, 150, 150),
            "items": [("re", pymupdf.Rect(100, 100, 150, 150))],
            "type": "s",
            "width": 1.0,
        }
        d2 = {
            "rect": pymupdf.Rect(155, 105, 200, 155),
            "items": [("re", pymupdf.Rect(155, 105, 200, 155))],
            "type": "s",
            "width": 1.0,
        }
        # Far primitive
        d3 = {
            "rect": pymupdf.Rect(400, 400, 480, 480),
            "items": [("re", pymupdf.Rect(400, 400, 480, 480))],
            "type": "s",
            "width": 1.0,
        }

        clusters = cluster_drawings([d1, d2, d3], distance_threshold=20.0)
        assert len(clusters) == 2
        # First cluster contains d1 and d2
        c0 = next(c for c in clusters if c.bbox.x1 == 100)
        assert len(c0.drawings) == 2
        assert c0.bbox.x2 == 200
        assert c0.bbox.y2 == 155

        # Second cluster contains d3
        c1 = next(c for c in clusters if c.bbox.x1 == 400)
        assert len(c1.drawings) == 1
        assert c1.bbox.x2 == 480

    def test_no_clipped_primitives_property(self):
        """Property: Every primitive in a cluster must be fully contained within the cluster bbox."""
        drawings = [
            {"rect": pymupdf.Rect(50, 60, 120, 130), "items": [], "type": "s", "width": 1},
            {"rect": pymupdf.Rect(110, 70, 180, 140), "items": [], "type": "s", "width": 1},
            {"rect": pymupdf.Rect(170, 80, 220, 150), "items": [], "type": "s", "width": 1},
        ]
        clusters = cluster_drawings(drawings, distance_threshold=15.0)
        assert len(clusters) == 1
        c = clusters[0]
        for d in drawings:
            r = d["rect"]
            assert c.bbox.x1 <= r.x0
            assert c.bbox.y1 <= r.y0
            assert c.bbox.x2 >= r.x1
            assert c.bbox.y2 >= r.y1


class TestSeparatorRuleFiltering:
    def test_horizontal_rule_filtered(self):
        """A thin line spanning > 50% of the page width is a separator, not a diagram."""
        d = {
            "rect": pymupdf.Rect(50, 100, 550, 101),
            "items": [("l", pymupdf.Point(50, 100.5), pymupdf.Point(550, 100.5))],
            "type": "s",
            "width": 1.0,
        }
        assert is_separator_rule(d, page_width=600, page_height=800) is True

    def test_vertical_column_rule_filtered(self):
        """A thin line spanning > 50% of page height is a column gutter rule."""
        d = {
            "rect": pymupdf.Rect(299, 100, 301, 700),
            "items": [("l", pymupdf.Point(300, 100), pymupdf.Point(300, 700))],
            "type": "s",
            "width": 1.0,
        }
        assert is_separator_rule(d, page_width=600, page_height=800) is True

    def test_diagram_box_not_filtered(self):
        """A diagram box (e.g. 150x120) is not a separator rule."""
        d = {
            "rect": pymupdf.Rect(100, 100, 250, 220),
            "items": [("re", pymupdf.Rect(100, 100, 250, 220))],
            "type": "s",
            "width": 1.0,
        }
        assert is_separator_rule(d, page_width=600, page_height=800) is False


class TestWatermarkVectorExclusion:
    def test_repeated_watermark_vector_hash(self):
        """Vectors that repeat across >= 3 pages with identical signature are identified as watermarks."""
        doc = pymupdf.open()
        for _ in range(4):
            p = doc.new_page(width=600, height=800)
            # Watermark line across the page
            p.draw_line(pymupdf.Point(50, 50), pymupdf.Point(550, 750), color=(0.8, 0.8, 0.8), width=1)
            # Page-unique diagram on page 2 only
            if p.number == 1:
                p.draw_rect(pymupdf.Rect(200, 200, 350, 350), color=(0, 0, 0), width=2)

        watermark_sigs = find_repeated_vector_signatures(doc, min_pages=3)
        assert len(watermark_sigs) >= 1

        # Page 2 drawings: watermark drawing is in watermark_sigs, diagram is not
        page2 = doc[1]
        drawings = page2.get_drawings()
        sigs = [compute_path_signature(d) for d in drawings]
        # At least one matches watermark_sigs and at least one does not
        assert any(s in watermark_sigs for s in sigs)
        assert any(s not in watermark_sigs for s in sigs)
        doc.close()


class TestExtractVectorFigures:
    def test_extract_circuit_and_save(self, tmp_path):
        """Extract a vector diagram, saving as SVG or high-DPI PNG."""
        doc = pymupdf.open()
        p = doc.new_page(width=600, height=800)
        # Draw a triangle and circle (optics prism)
        p.draw_line(pymupdf.Point(150, 200), pymupdf.Point(250, 200), color=(0, 0, 0), width=2)
        p.draw_line(pymupdf.Point(250, 200), pymupdf.Point(200, 120), color=(0, 0, 0), width=2)
        p.draw_line(pymupdf.Point(200, 120), pymupdf.Point(150, 200), color=(0, 0, 0), width=2)
        p.draw_circle(pymupdf.Point(200, 170), 15, color=(0, 0, 0), width=1)

        figs = extract_vector_figures(
            doc=doc,
            page=p,
            page_num=1,
            output_dir=tmp_path,
            watermark_signatures=set(),
        )

        assert len(figs) == 1
        fig = figs[0]
        assert fig.page == 1
        assert fig.bbox.width >= 90
        assert fig.bbox.height >= 70
        assert Path(fig.crop_path).exists()
        assert fig.classification == FigureClass.DIAGRAM
        doc.close()
