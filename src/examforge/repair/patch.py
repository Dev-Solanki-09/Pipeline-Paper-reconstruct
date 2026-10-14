"""Constrained RFC 6902 JSON patch applier with safety guards and validation."""

from __future__ import annotations

import logging
import re
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, Question

logger = logging.getLogger(__name__)

ALLOWED_PATH_PATTERNS = [
    re.compile(r"^/stem_text_(en|hi)$"),
    re.compile(r"^/options/(\d+)/text_str_(en|hi)$"),
    re.compile(r"^/options/(\d+)/label$"),
    re.compile(r"^/answer/(correct_options|numeric_value|numeric_range)$"),
]


class UnsafePatchError(Exception):
    """Raised when a patch attempts to modify immutable fields or violates guards."""


class InvalidPatchError(Exception):
    """Raised when a patch format is malformed or invalid."""


class NewBlockerIntroducedError(Exception):
    """Raised when applying a patch causes a new blocker validation failure."""


def _is_path_allowed(path: str) -> bool:
    """Verify if a JSON pointer path is in the safety allow-list."""
    return any(p.match(path) for p in ALLOWED_PATH_PATTERNS)


def _check_digits_preserved(old_text: str, new_text: str, issue: Issue) -> None:
    """Enforce digit-preserving invariant unless the issue specifically targets digits."""
    if issue.rule in ("digits", "numbering", "sequence_gaps"):
        return

    old_digits = sorted(re.findall(r"\d", str(old_text)))
    new_digits = sorted(re.findall(r"\d", str(new_text)))
    if old_digits != new_digits:
        raise UnsafePatchError(
            f"Digit-preserving guard failed: original digits {old_digits} "
            f"!= new digits {new_digits}"
        )


def apply_patch_to_question(
    question: Question,
    patches: list[dict[str, Any]],
    issue: Issue,
    doc: ExamDocument | None = None,
) -> Question:
    """
    Apply a list of RFC 6902 patch operations to a question slice.

    Safety constraints enforced:
    1. Allow-listed paths only (/stem_text_*, /options/*/text_str_*, etc.).
    2. Immutable fields (/id, /number) are forbidden.
    3. Digit-preserving guard for text edits.
    4. Scoped validator re-run to revert if a new blocker appears.
    """
    if not isinstance(patches, list):
        raise InvalidPatchError("Patches must be a list of patch operations")

    # 1. Path allow-list verification
    for p in patches:
        path = p.get("path", "")
        op = p.get("op", "")
        if not path or not op:
            raise InvalidPatchError(f"Malformed patch operation: {p}")
        if not _is_path_allowed(path):
            raise UnsafePatchError(f"Forbidden patch path: {path}")

    # 2. Make deep copy to permit atomic rollback
    q_copy = question.model_copy(deep=True)

    # 3. Apply operations
    for p in patches:
        op = p["op"]
        path = p["path"]
        val = p.get("value")

        if op != "replace":
            raise InvalidPatchError(f"Unsupported patch operation: {op}")

        # Stem edits
        if path == "/stem_text_en":
            _check_digits_preserved(q_copy.stem_text_en, val, issue)
            q_copy.stem_text_en = str(val)
        elif path == "/stem_text_hi":
            _check_digits_preserved(q_copy.stem_text_hi, val, issue)
            q_copy.stem_text_hi = str(val)

        # Option text edits
        opt_match = re.match(r"^/options/(\d+)/text_str_(en|hi)$", path)
        if opt_match:
            idx = int(opt_match.group(1))
            lang = opt_match.group(2)
            if idx >= len(q_copy.options):
                raise InvalidPatchError(f"Option index {idx} out of bounds")
            field_name = f"text_str_{lang}"
            old_val = getattr(q_copy.options[idx], field_name)
            _check_digits_preserved(old_val, val, issue)
            setattr(q_copy.options[idx], field_name, str(val))

        # Option label edits
        opt_lbl_match = re.match(r"^/options/(\d+)/label$", path)
        if opt_lbl_match:
            idx = int(opt_lbl_match.group(1))
            if idx >= len(q_copy.options):
                raise InvalidPatchError(f"Option index {idx} out of bounds")
            q_copy.options[idx].label = str(val)

    # 4. Scoped validation re-run if document context provided
    if doc is not None:
        from examforge.validators.registry import get_validator

        # Create temporary doc with patched question
        temp_questions = [
            q_copy if q.id == question.id else q for q in doc.questions
        ]
        temp_doc = doc.model_copy(update={"questions": temp_questions})

        # Run relevant validator for issue.rule
        validator_fn = get_validator(issue.rule)
        if validator_fn:
            new_issues = validator_fn(temp_doc)
            new_blockers = [
                i for i in new_issues if i.severity == IssueSeverity.BLOCKER
            ]
            # If new blocker introduced, reject patch
            if len(new_blockers) > 0 and not any(i.id == issue.id for i in new_blockers):
                raise NewBlockerIntroducedError(
                    f"Patch introduced new blocker: {new_blockers[0].message}"
                )

    return q_copy
