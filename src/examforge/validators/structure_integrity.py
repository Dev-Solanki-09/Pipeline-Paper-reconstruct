"""
Consolidated Validator: structure_integrity (Phase O4.2).

Merges R06 (numbering continuity), R14 (sequence gaps and bounds), and R15 (structure consistency)
into a unified structural integrity verification pass.
CostTier: FREE.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, Question, QuestionKind, TextNode
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

logger = logging.getLogger(__name__)

# Sub-part label extraction
SUBPART_LABEL_RE = re.compile(r"^\(?([a-zA-Z]|[ivxlcdmIVXLCDM]+|[0-9]+)\)?[\.:\s]")


def _get_subpart_key(q: Question) -> str | None:
    """Extract sub-part label or sequence index."""
    if q.original_number is not None:
        return str(q.original_number)
    stem_txt = q.stem_text_en or (q.stem[0].texts.get("en", "") if q.stem and isinstance(q.stem[0], TextNode) else "")
    m = SUBPART_LABEL_RE.match(stem_txt.strip())
    if m:
        return m.group(1).lower()
    return None


@register_validator(
    "structure_integrity",
    cost_tier=CostTier.FREE,
    aliases=["numbering_continuity", "sequence_gaps", "structure_consistency"],
)
def validate_structure_integrity(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """
    Consolidated verification of:
    1. Numbering continuity, sequence gaps, duplicates (R06 + R14).
    2. Sub-part ordering, choice groups, passages, question kinds (R15).
    """
    issues: list[Issue] = []
    severity = (
        IssueSeverity.BLOCKER
        if (rule and getattr(rule.severity, "value", str(rule.severity)) == "blocker")
        else IssueSeverity.WARNING
    )
    rule_name = rule.check if rule and rule.check else "structure_integrity"
    params = rule.params if rule and rule.params else {}

    questions = sorted(document.questions, key=lambda q: q.number)
    if not questions:
        expected_total = params.get("expected_total_questions", 0)
        if expected_total > 0:
            issues.append(
                Issue(
                    id="r14_no_questions_found",
                    stage="s8_verify",
                    rule=rule_name,
                    severity=severity,
                    message=f"Rule R14: Document has 0 questions, expected {expected_total}",
                    evidence={"expected_total": expected_total, "actual": 0},
                )
            )
        return issues

    run_numbering = rule_name in ("structure_integrity", "numbering_continuity", "sequence_gaps")
    run_structure = rule_name in ("structure_integrity", "structure_consistency")

    # ---------------------------------------------------------
    # 1. Duplicates & Numbering Gaps (R06 + R14)
    # ---------------------------------------------------------
    if run_numbering:
        seen_by_num: dict[int, list[Question]] = {}
        for q in questions:
            seen_by_num.setdefault(q.number, []).append(q)

        # 1a. Duplicate question numbers
        for num, q_list in sorted(seen_by_num.items()):
            if len(q_list) > 1:
                q_ids = [q.id for q in q_list]
                pages = [q.source_pages for q in q_list]
                issues.append(
                    Issue(
                        id=f"r14_duplicate_q{num}",
                        stage="s8_verify",
                        rule="numbering_continuity" if rule_name == "numbering_continuity" else "sequence_gaps",
                        severity=severity,
                        message=f"Rule R14: Duplicate question number {num} found ({len(q_list)} instances)",
                        evidence={"number": num, "question_ids": q_ids, "pages": pages},
                    )
                )

        # 1b. Missing question numbers (gaps)
        min_num = questions[0].number
        max_num = questions[-1].number
        actual_nums = set(seen_by_num.keys())
        full_range = set(range(min_num, max_num + 1))
        missing_nums = sorted(full_range - actual_nums)

        if missing_nums:
            # Compute spatial neighborhood bounds
            for m_num in missing_nums:
                prev_q = next((q for q in reversed(questions) if q.number < m_num), None)
                next_q = next((q for q in questions if q.number > m_num), None)
                prev_page = prev_q.source_pages[-1] if (prev_q and prev_q.source_pages) else None
                next_page = next_q.source_pages[0] if (next_q and next_q.source_pages) else None

                issues.append(
                    Issue(
                        id=f"r14_gap_q{m_num}",
                        stage="s8_verify",
                        rule="numbering_continuity" if rule_name == "numbering_continuity" else "sequence_gaps",
                        severity=severity,
                        message=f"Rule R14: Missing question number {m_num} in sequence {min_num}..{max_num}",
                        evidence={
                            "missing_number": m_num,
                            "missing_questions": [m_num],
                            "prev_question": prev_q.id if prev_q else None,
                            "next_question": next_q.id if next_q else None,
                            "page_neighborhood": [prev_page, next_page],
                        },
                    )
                )

    # ---------------------------------------------------------
    # 2. Structural Consistency & Constraints (R15)
    # ---------------------------------------------------------
    if not run_structure:
        return issues

    # 2a. Collect passage IDs
    valid_passage_ids = {p.id for p in document.passages}
    for part in document.parts:
        if getattr(part, "kind", None) == "passage":
            valid_passage_ids.add(part.id)

    # 2b. Collect choice groups
    choice_groups: dict[str, list[Question]] = {}
    for q in questions:
        if q.choice_group:
            choice_groups.setdefault(q.choice_group, []).append(q)

    for group_name, members in choice_groups.items():
        if len(members) < 2:
            issues.append(
                Issue(
                    id=f"r15_choice_orphan_{group_name}",
                    stage="s8_verify",
                    rule="structure_consistency",
                    severity=IssueSeverity.WARNING,
                    message=f"Rule R15: Choice group '{group_name}' has only 1 question ({members[0].id}); requires >= 2 alternatives",
                    evidence={"choice_group": group_name, "questions": [m.id for m in members]},
                )
            )

    # 2c. Per-question structural checks
    for q in questions:
        # Subpart label sequencing
        if q.children:
            sub_keys = [_get_subpart_key(child) for child in q.children]
            valid_keys = [k for k in sub_keys if k is not None]
            if len(valid_keys) >= 2 and all(len(k) == 1 and k.isalpha() for k in valid_keys):
                ord_vals = [ord(k.lower()) - ord("a") for k in valid_keys]
                expected_range = list(range(ord_vals[0], ord_vals[0] + len(ord_vals)))
                if ord_vals != expected_range:
                    issues.append(
                        Issue(
                            id=f"r15_subpart_gap_{q.id}",
                            stage="s8_verify",
                            rule="structure_consistency",
                            question_id=q.id,
                            severity=severity,
                            message=f"Rule R15: Question {q.number} has non-sequential subpart labels: {valid_keys}",
                            evidence={"subparts": valid_keys},
                        )
                    )

        # Passage ref resolution
        if q.passage_ref and q.passage_ref not in valid_passage_ids:
            issues.append(
                Issue(
                    id=f"r15_missing_passage_{q.id}",
                    stage="s8_verify",
                    rule="structure_consistency",
                    question_id=q.id,
                    severity=severity,
                    message=f"Rule R15: Question {q.number} references non-existent passage '{q.passage_ref}'",
                    evidence={"passage_ref": q.passage_ref},
                )
            )

        # QuestionKind shape checks
        kind = q.kind
        opts_count = len(q.options)

        if kind in (QuestionKind.SINGLE_CORRECT, QuestionKind.MULTI_CORRECT):
            if opts_count < 2:
                issues.append(
                    Issue(
                        id=f"r15_mcq_opts_{q.id}",
                        stage="s8_verify",
                        rule="structure_consistency",
                        question_id=q.id,
                        severity=severity,
                        message=f"Rule R15: MCQ Question {q.number} must have >= 2 options (found {opts_count})",
                        evidence={"kind": kind.value, "options_count": opts_count},
                    )
                )
        elif kind == QuestionKind.NUMERICAL:
            if opts_count > 0:
                issues.append(
                    Issue(
                        id=f"r15_numerical_opts_{q.id}",
                        stage="s8_verify",
                        rule="structure_consistency",
                        question_id=q.id,
                        severity=severity,
                        message=f"Rule R15: Numerical Question {q.number} must NOT have multiple choice options (found {opts_count})",
                        evidence={"options_count": opts_count},
                    )
                )
        elif kind == QuestionKind.MATCH:
            has_match_node = any(node.kind == "match_columns" for node in q.stem)
            has_table_ref = bool(q.table_refs)
            if not has_match_node and not has_table_ref:
                issues.append(
                    Issue(
                        id=f"r15_match_no_cols_{q.id}",
                        stage="s8_verify",
                        rule="structure_consistency",
                        question_id=q.id,
                        severity=IssueSeverity.WARNING,
                        message=f"Rule R15: Match Question {q.number} lacks match_columns node or table reference",
                        evidence={"kind": kind.value},
                    )
                )

    return issues
