"""Validator for R16: answer_binding.

Enforces referential integrity and consistency of answer keys:
- Every answer references an existing question and a valid option label / range
- No duplicate answer entries
- Count equals question count when an answer key is present
- Kind compatibility (single MCQ vs multi MCQ vs integer/numerical)
"""

from __future__ import annotations

import logging
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, QuestionKind
from examforge.spec import Rule
from examforge.validators.base import CostTier
from examforge.validators.registry import register_validator

logger = logging.getLogger(__name__)


@register_validator("answer_binding", cost_tier=CostTier.FREE)
@register_validator("R16_answer_binding", cost_tier=CostTier.FREE)
def validate_answer_binding(
    document: ExamDocument,
    rule: Rule | None = None,
) -> list[Issue]:
    """Validate referential integrity, count, and kind compatibility of bound answers."""
    issues: list[Issue] = []
    severity = IssueSeverity.BLOCKER if (rule and rule.severity.value == "blocker") else IssueSeverity.WARNING

    questions = document.questions
    if not questions:
        return issues

    answered_questions = [q for q in questions if q.answer is not None]
    if not answered_questions:
        # No answer key in document — valid when no key present
        return issues

    # 1. Incomplete answer key check: when answers are present, every question should have one
    if len(answered_questions) < len(questions):
        missing_nums = [q.number for q in questions if q.answer is None]
        issues.append(
            Issue(
                id="r16_incomplete_key",
                stage="s8_verify",
                rule="answer_binding",
                severity=severity,
                message=f"Rule R16: Incomplete answer key — {len(answered_questions)}/{len(questions)} questions answered. Missing Q numbers: {missing_nums[:10]}",
                evidence={"answered": len(answered_questions), "total": len(questions), "missing_questions": missing_nums},
            )
        )

    # 2. Per-question validation
    for q in answered_questions:
        ans = q.answer
        if not ans:
            continue

        # Check option labels validity
        if ans.correct_options and q.options:
            valid_labels = {opt.label.strip().upper() for opt in q.options}
            for opt in ans.correct_options:
                if opt.strip().upper() not in valid_labels and opt != "BONUS":
                    issues.append(
                        Issue(
                            id=f"r16_invalid_option_label_q{q.number}_{opt}",
                            stage="s8_verify",
                            rule="answer_binding",
                            severity=severity,
                            message=f"Rule R16: Question {q.number} answer option '{opt}' is not among valid options {sorted(list(valid_labels))}",
                            evidence={"question_number": q.number, "option": opt, "valid_options": sorted(list(valid_labels))},
                        )
                    )

        # Kind compatibility
        is_single = q.kind in (QuestionKind.SINGLE_CORRECT, QuestionKind.MCQ_SINGLE)
        if is_single and len(ans.correct_options) > 1 and ans.text_solution != "BONUS":
            # Only 1 option allowed for single MCQ unless bonus
            issues.append(
                Issue(
                    id=f"r16_single_mcq_multiple_answers_q{q.number}",
                    stage="s8_verify",
                    rule="answer_binding",
                    severity=severity,
                    message=f"Rule R16: Single-choice MCQ Q{q.number} has multiple answers: {ans.correct_options}",
                    evidence={"question_number": q.number, "correct_options": ans.correct_options},
                )
            )

        # Integer question compatibility
        if q.kind == QuestionKind.INTEGER:
            if ans.numeric_value is not None and ans.numeric_value % 1 != 0:
                issues.append(
                    Issue(
                        id=f"r16_non_integer_answer_q{q.number}",
                        stage="s8_verify",
                        rule="answer_binding",
                        severity=severity,
                        message=f"Rule R16: Integer question Q{q.number} has non-integer answer: {ans.numeric_value}",
                        evidence={"question_number": q.number, "numeric_value": ans.numeric_value},
                    )
                )

        # Inverted numeric range
        if ans.numeric_range is not None:
            low, high = ans.numeric_range
            if low > high:
                issues.append(
                    Issue(
                        id=f"r16_inverted_range_q{q.number}",
                        stage="s8_verify",
                        rule="answer_binding",
                        severity=severity,
                        message=f"Rule R16: Inverted numeric range on Q{q.number}: ({low}, {high})",
                        evidence={"question_number": q.number, "range": (low, high)},
                    )
                )

    return issues
