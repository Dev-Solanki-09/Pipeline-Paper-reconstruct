"""Tables pipeline: structure reconstruction and safe fallback (Zero Silent Loss)."""

from __future__ import annotations

from examforge.ir.schema import (
    BBox,
    Block,
    RawCropNode,
    TableNode,
)
from examforge.tables.grid import TableGrid, build_table_from_rulings


def validate_table_structure(grid: TableGrid | None) -> bool:
    """Validate that a reconstructed TableGrid has coherent rectangular structure."""
    if grid is None:
        return False

    if grid.num_rows < 2 or grid.num_cols < 2:
        return False

    total_cells = grid.num_rows * grid.num_cols
    non_empty_cells = sum(
        1 for row in grid.cells for cell in row if cell.text.strip()
    )

    # Require at least 50% non-empty cells for high confidence
    if non_empty_cells < max(1, total_cells * 0.4):
        return False

    return True


def process_table_candidates(
    h_lines: list[tuple[float, float, float, float]],
    v_lines: list[tuple[float, float, float, float]],
    text_blocks: list[Block] | None = None,
    table_bbox: BBox | None = None,
    figure_ref: str = "",
) -> TableNode | RawCropNode:
    """Process table rulings and text blocks into TableNode or degrade safely to RawCropNode.

    Zero Silent Loss: If table structure cannot be determined with high confidence,
    it degrades to a RawCropNode pointing to the table figure crop with an explicit reason.
    """
    grid = build_table_from_rulings(h_lines, v_lines, text_blocks=text_blocks)

    if validate_table_structure(grid):
        assert grid is not None
        return grid.to_table_node()

    return RawCropNode(
        figure_ref=figure_ref,
        reason="table_structure_low_confidence",
    )
