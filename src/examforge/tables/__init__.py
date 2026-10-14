"""ExamForge tables package: rulings to grid, alignment, and safe degradation."""

from __future__ import annotations

from examforge.tables.grid import TableGrid, build_table_from_rulings
from examforge.tables.pipeline import (
    process_table_candidates,
    validate_table_structure,
)
from examforge.tables.vector import extract_rulings_from_drawings

__all__ = [
    "TableGrid",
    "build_table_from_rulings",
    "extract_rulings_from_drawings",
    "process_table_candidates",
    "validate_table_structure",
]
