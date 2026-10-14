"""Tests for tables pipeline (vector rulings to grid, text alignment, and safe degradation)."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    BBox,
    Block,
    Cell,
    RawCropNode,
    TableNode,
)
from examforge.tables.grid import TableGrid, build_table_from_rulings
from examforge.tables.pipeline import (
    process_table_candidates,
    validate_table_structure,
)


class TestVectorRulingsToGrid:
    def test_2x2_ruled_table(self):
        """3 horizontal and 3 vertical rulings form a 2x2 grid."""
        h_lines = [
            (50.0, 100.0, 350.0, 100.0),   # top
            (50.0, 150.0, 350.0, 150.0),   # middle
            (50.0, 200.0, 350.0, 200.0),   # bottom
        ]
        v_lines = [
            (50.0, 100.0, 50.0, 200.0),    # left
            (200.0, 100.0, 200.0, 200.0),  # middle
            (350.0, 100.0, 350.0, 200.0),  # right
        ]

        text_blocks = [
            Block(id="t00", page=1, bbox=BBox(x1=60, y1=110, x2=190, y2=140), text="Column A"),
            Block(id="t01", page=1, bbox=BBox(x1=210, y1=110, x2=340, y2=140), text="Column B"),
            Block(id="t10", page=1, bbox=BBox(x1=60, y1=160, x2=190, y2=190), text="Value 1"),
            Block(id="t11", page=1, bbox=BBox(x1=210, y1=160, x2=340, y2=190), text="Value 2"),
        ]

        grid = build_table_from_rulings(h_lines, v_lines, text_blocks=text_blocks)
        assert grid is not None
        assert grid.num_rows == 2
        assert grid.num_cols == 2
        assert grid.cells[0][0].text == "Column A"
        assert grid.cells[0][1].text == "Column B"
        assert grid.cells[1][0].text == "Value 1"
        assert grid.cells[1][1].text == "Value 2"

    def test_header_row_detection(self):
        """Header-like text in top row sets header_rows=1."""
        h_lines = [
            (50.0, 100.0, 350.0, 100.0),
            (50.0, 150.0, 350.0, 150.0),
            (50.0, 200.0, 350.0, 200.0),
        ]
        v_lines = [
            (50.0, 100.0, 50.0, 200.0),
            (200.0, 100.0, 200.0, 200.0),
            (350.0, 100.0, 350.0, 200.0),
        ]
        text_blocks = [
            Block(id="t00", page=1, bbox=BBox(x1=60, y1=110, x2=190, y2=140), text="List I"),
            Block(id="t01", page=1, bbox=BBox(x1=210, y1=110, x2=340, y2=140), text="List II"),
            Block(id="t10", page=1, bbox=BBox(x1=60, y1=160, x2=190, y2=190), text="(A) Option A"),
            Block(id="t11", page=1, bbox=BBox(x1=210, y1=160, x2=340, y2=190), text="(i) Match 1"),
        ]

        grid = build_table_from_rulings(h_lines, v_lines, text_blocks=text_blocks)
        table_node = grid.to_table_node()
        assert isinstance(table_node, TableNode)
        assert table_node.header_rows == 1


class TestSafeDegradationToRawCrop:
    def test_malformed_table_degrades_to_raw_crop(self):
        """When table structure is ambiguous or fails validation, degrade to RawCropNode (Zero Silent Loss)."""
        # Ambiguous rulings (e.g. only 1 horizontal line, cannot form closed grid)
        h_lines = [(50.0, 100.0, 350.0, 100.0)]
        v_lines = [(50.0, 100.0, 50.0, 200.0)]
        bbox = BBox(x1=50, y1=100, x2=350, y2=200)

        node = process_table_candidates(
            h_lines=h_lines,
            v_lines=v_lines,
            text_blocks=[],
            table_bbox=bbox,
            figure_ref="fig_tbl_1",
        )

        assert isinstance(node, RawCropNode)
        assert node.figure_ref == "fig_tbl_1"
        assert node.reason == "table_structure_low_confidence"
