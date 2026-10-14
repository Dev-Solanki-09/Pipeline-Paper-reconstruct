"""Table grid representation, cell alignment, and header detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from examforge.ir.schema import (
    BBox,
    Block,
    Cell,
    Lang,
    TableNode,
)

_HEADER_KEYWORDS_RE = re.compile(
    r"\b(list\s*(i|ii|1|2)|column\s*(i|ii|1|2)|स्तम्भ\s*(i|ii|1|2)|property|value|item|match|statement|type|name)\b",
    re.IGNORECASE,
)


@dataclass
class TableGrid:
    """Internal grid representation for table reconstruction."""

    cells: list[list[Cell]] = field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0
    header_rows: int = 0
    spans: list[dict[str, Any]] = field(default_factory=list)

    def to_table_node(self) -> TableNode:
        """Convert to canonical IR TableNode."""
        return TableNode(
            rows=self.cells,
            header_rows=self.header_rows,
            spans=self.spans,
        )


def _cluster_coords(coords: list[float], tolerance: float = 4.0) -> list[float]:
    """Cluster 1D coordinates within tolerance and return sorted cluster centers."""
    if not coords:
        return []
    sorted_c = sorted(coords)
    clusters: list[list[float]] = [[sorted_c[0]]]
    for c in sorted_c[1:]:
        if c - clusters[-1][-1] <= tolerance:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    return [sum(cl) / len(cl) for cl in clusters]


def build_table_from_rulings(
    h_lines: list[tuple[float, float, float, float]],
    v_lines: list[tuple[float, float, float, float]],
    text_blocks: list[Block] | None = None,
) -> TableGrid | None:
    """Build a TableGrid from intersecting horizontal and vertical rulings."""
    if len(h_lines) < 2 or len(v_lines) < 2:
        return None

    y_coords = _cluster_coords([hl[1] for hl in h_lines])
    x_coords = _cluster_coords([vl[0] for vl in v_lines])

    num_rows = len(y_coords) - 1
    num_cols = len(x_coords) - 1

    if num_rows < 1 or num_cols < 1:
        return None

    # Initialize empty grid of Cells
    grid_cells: list[list[Cell]] = [
        [Cell(text="", lang=Lang.UNKNOWN, colspan=1, rowspan=1) for _ in range(num_cols)]
        for _ in range(num_rows)
    ]

    # Assign text blocks to cells
    if text_blocks:
        for block in text_blocks:
            bx = (block.bbox.x1 + block.bbox.x2) / 2.0
            by = (block.bbox.y1 + block.bbox.y2) / 2.0

            # Find row index
            r_idx = -1
            for r in range(num_rows):
                if y_coords[r] - 2 <= by <= y_coords[r + 1] + 2:
                    r_idx = r
                    break

            # Find col index
            c_idx = -1
            for c in range(num_cols):
                if x_coords[c] - 2 <= bx <= x_coords[c + 1] + 2:
                    c_idx = c
                    break

            if r_idx != -1 and c_idx != -1:
                cur_text = grid_cells[r_idx][c_idx].text
                new_text = (cur_text + " " + block.text).strip() if cur_text else block.text.strip()
                grid_cells[r_idx][c_idx].text = new_text

    # Header row detection
    header_rows = 0
    if num_rows >= 2:
        first_row_text = " ".join(c.text for c in grid_cells[0])
        if _HEADER_KEYWORDS_RE.search(first_row_text):
            header_rows = 1

    return TableGrid(
        cells=grid_cells,
        num_rows=num_rows,
        num_cols=num_cols,
        header_rows=header_rows,
        spans=[],
    )
