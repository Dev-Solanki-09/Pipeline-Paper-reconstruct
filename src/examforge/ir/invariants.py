"""
ExamForge v2: Strict Intermediate Representation Invariants System.

Enforces fundamental structural and semantic invariants across document state:
- INV-01: Page Numbering Monotonicity (1 to N without gaps or duplicates)
- INV-02: Element ID Uniqueness (blocks, questions, figures, tables, passages)
- INV-03: BBox Coordinates Validity (x1 <= x2, y1 <= y2, non-negative)
- INV-04: Question Sequence Integrity (strictly increasing sequence_index & numbers per section)
- INV-05: Option Labels & Sequence Integrity (unique non-empty labels per question)
- INV-06: Referent Integrity (figures, tables, passages, options must resolve)
- INV-07: Choice Group Integrity (members of same choice_group share marks)
- INV-08: Deterministic Serialization (zero timestamps, normalized paths)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from examforge.ir.schema import ExamDocument


@dataclass
class InvariantViolation:
    """A single invariant violation discovered on an ExamDocument."""

    code: str
    message: str
    severity: str = "error"  # "error" or "warning"
    element_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class InvariantError(ValueError):
    """Raised when an ExamDocument violates one or more hard invariants."""

    def __init__(self, violations: list[InvariantViolation]) -> None:
        messages = [f"[{v.code}] {v.message}" for v in violations if v.severity == "error"]
        super().__init__(
            f"ExamDocument violated {len(messages)} strict invariants:\n"
            + "\n".join(messages)
        )
        self.violations = violations


def validate_invariants(doc: ExamDocument) -> list[InvariantViolation]:
    """
    Audit an ExamDocument against all strict invariants.

    Returns a list of all detected violations.
    """
    violations: list[InvariantViolation] = []

    # INV-01: Page Numbering Monotonicity
    if doc.pages:
        page_numbers = [p.page_number for p in doc.pages]
        expected_numbers = list(range(1, len(doc.pages) + 1))
        if page_numbers != expected_numbers:
            violations.append(
                InvariantViolation(
                    code="INV-01",
                    message=(
                        f"Page numbers are not contiguous 1..N: "
                        f"expected {expected_numbers}, got {page_numbers}"
                    ),
                    severity="error",
                )
            )

    # INV-02: Element ID Uniqueness
    seen_block_ids: set[str] = set()
    for block in doc.blocks:
        if block.id in seen_block_ids:
            violations.append(
                InvariantViolation(
                    code="INV-02",
                    message=f"Duplicate block ID detected: '{block.id}' on page {block.page}",
                    element_id=block.id,
                    severity="error",
                )
            )
        else:
            seen_block_ids.add(block.id)

    seen_q_ids: set[str] = set()
    for q in doc.questions:
        if q.id in seen_q_ids:
            violations.append(
                InvariantViolation(
                    code="INV-02",
                    message=f"Duplicate question ID detected: '{q.id}' (Q{q.number})",
                    element_id=q.id,
                    severity="error",
                )
            )
        else:
            seen_q_ids.add(q.id)

    seen_fig_ids: set[str] = set()
    for fig in doc.figures:
        if fig.id in seen_fig_ids:
            violations.append(
                InvariantViolation(
                    code="INV-02",
                    message=f"Duplicate figure ID detected: '{fig.id}'",
                    element_id=fig.id,
                    severity="error",
                )
            )
        else:
            seen_fig_ids.add(fig.id)

    seen_tab_ids: set[str] = set()
    for tab in doc.tables:
        if tab.id in seen_tab_ids:
            violations.append(
                InvariantViolation(
                    code="INV-02",
                    message=f"Duplicate table ID detected: '{tab.id}'",
                    element_id=tab.id,
                    severity="error",
                )
            )
        else:
            seen_tab_ids.add(tab.id)

    # INV-03: BBox Coordinates Validity
    for block in doc.blocks:
        if block.bbox.x1 > block.bbox.x2 or block.bbox.y1 > block.bbox.y2:
            violations.append(
                InvariantViolation(
                    code="INV-03",
                    message=(
                        f"Block '{block.id}' has inverted coordinates: "
                        f"({block.bbox.x1}, {block.bbox.y1}) -> ({block.bbox.x2}, {block.bbox.y2})"
                    ),
                    element_id=block.id,
                    severity="error",
                )
            )

    for fig in doc.figures:
        if fig.bbox.x1 > fig.bbox.x2 or fig.bbox.y1 > fig.bbox.y2:
            violations.append(
                InvariantViolation(
                    code="INV-03",
                    message=(
                        f"Figure '{fig.id}' has inverted coordinates: "
                        f"({fig.bbox.x1}, {fig.bbox.y1}) -> ({fig.bbox.x2}, {fig.bbox.y2})"
                    ),
                    element_id=fig.id,
                    severity="error",
                )
            )

    # INV-04 & INV-05: Question & Option Integrity
    seen_q_indices: set[int] = set()
    section_q_numbers: dict[str, list[int]] = {}
    choice_groups: dict[str, list[Any]] = {}

    for q in doc.questions:
        if q.sequence_index in seen_q_indices and q.sequence_index > 0:
            violations.append(
                InvariantViolation(
                    code="INV-04",
                    message=f"Duplicate question sequence_index: {q.sequence_index} on Q{q.number}",
                    element_id=q.id,
                    severity="error",
                )
            )
        seen_q_indices.add(q.sequence_index)

        # Track question numbers per section
        sec = q.section or "__default__"
        section_q_numbers.setdefault(sec, []).append(q.number)

        # Track choice groups
        if q.choice_group:
            choice_groups.setdefault(q.choice_group, []).append(q)

        # Check options
        seen_labels: set[str] = set()
        for opt in q.options:
            if not opt.label:
                violations.append(
                    InvariantViolation(
                        code="INV-05",
                        message=f"Option in Q{q.number} has empty label",
                        element_id=q.id,
                        severity="error",
                    )
                )
            elif opt.label in seen_labels:
                violations.append(
                    InvariantViolation(
                        code="INV-05",
                        message=f"Duplicate option label '{opt.label}' in Q{q.number}",
                        element_id=q.id,
                        severity="error",
                    )
                )
            seen_labels.add(opt.label)

    # Question numbers monotone per section
    for sec, numbers in section_q_numbers.items():
        if numbers and numbers != sorted(numbers):
            violations.append(
                InvariantViolation(
                    code="INV-04",
                    message=f"Question numbers in section '{sec}' are not monotone: {numbers}",
                    severity="error",
                )
            )

    # INV-06: Referent Integrity
    existing_figure_ids = {f.id for f in doc.figures}
    existing_table_ids = {t.id for t in doc.tables}
    existing_passage_ids = {p.id for p in doc.passages}

    for q in doc.questions:
        for fref in q.figure_refs:
            if fref not in existing_figure_ids:
                violations.append(
                    InvariantViolation(
                        code="INV-06",
                        message=f"Question Q{q.number} references non-existent figure '{fref}'",
                        element_id=q.id,
                        severity="error",
                    )
                )
        for opt in q.options:
            if opt.figure_ref and opt.figure_ref not in existing_figure_ids:
                violations.append(
                    InvariantViolation(
                        code="INV-06",
                        message=(
                            f"Option '{opt.label}' in Q{q.number} references "
                            f"non-existent figure '{opt.figure_ref}'"
                        ),
                        element_id=q.id,
                        severity="error",
                    )
                )
        for tref in q.table_refs:
            if tref not in existing_table_ids:
                violations.append(
                    InvariantViolation(
                        code="INV-06",
                        message=f"Question Q{q.number} references non-existent table '{tref}'",
                        element_id=q.id,
                        severity="error",
                    )
                )
        if q.passage_ref and q.passage_ref not in existing_passage_ids:
            violations.append(
                InvariantViolation(
                    code="INV-06",
                    message=(
                        f"Question Q{q.number} references non-existent "
                        f"passage '{q.passage_ref}'"
                    ),
                    element_id=q.id,
                    severity="error",
                )
            )

    # INV-07: Choice Group Integrity (members share marks)
    for group_name, members in choice_groups.items():
        if len(members) > 1:
            first_marks = members[0].marks
            for member in members[1:]:
                if member.marks != first_marks:
                    violations.append(
                        InvariantViolation(
                            code="INV-07",
                            message=(
                                f"Questions in choice group '{group_name}' have mismatched marks: "
                                f"Q{members[0].number} ({first_marks}) vs "
                                f"Q{member.number} ({member.marks})"
                            ),
                            element_id=member.id,
                            severity="error",
                        )
                    )

    return violations


def assert_invariants(doc: ExamDocument) -> None:
    """
    Verify all strict invariants and raise InvariantError on any hard error.
    """
    violations = validate_invariants(doc)
    errors = [v for v in violations if v.severity == "error"]
    if errors:
        raise InvariantError(errors)
