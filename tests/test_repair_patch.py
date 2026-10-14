"""Tests for constrained RFC 6902 patch applier with safety guards."""

from __future__ import annotations

import pytest

from examforge.ir.schema import (
    Issue,
    IssueSeverity,
    Option,
    Question,
    QuestionKind,
)
from examforge.repair.patch import (
    UnsafePatchError,
    apply_patch_to_question,
)


def _make_sample_question() -> Question:
    return Question(
        id="q_1",
        number=1,
        kind=QuestionKind.SINGLE_CORRECT,
        stem_text_en="Speed of sound is 343 m/s in air at 20 C.",
        options=[
            Option(label="A", text_str_en="343 m/s"),
            Option(label="B", text_str_en="300 m/s"),
        ],
        source_pages=[1],
    )


class TestRepairPatchApplier:
    def test_apply_valid_stem_replace(self):
        q = _make_sample_question()
        issue = Issue(
            id="i1", stage="s8", rule="lexicon", severity=IssueSeverity.WARNING, message="lex error"
        )
        patches = [
            {
                "op": "replace",
                "path": "/stem_text_en",
                "value": "Speed of sound is 343 m/s in air at 20 C.",
            },
        ]
        patched = apply_patch_to_question(q, patches, issue)
        assert patched.stem_text_en == "Speed of sound is 343 m/s in air at 20 C."

    def test_reject_forbidden_path_id(self):
        q = _make_sample_question()
        issue = Issue(
            id="i2", stage="s8", rule="text_layer", severity=IssueSeverity.BLOCKER, message="err"
        )
        patches = [
            {"op": "replace", "path": "/id", "value": "q_hijacked"},
        ]
        with pytest.raises(UnsafePatchError):
            apply_patch_to_question(q, patches, issue)

    def test_reject_forbidden_path_number(self):
        q = _make_sample_question()
        issue = Issue(
            id="i3", stage="s8", rule="text_layer", severity=IssueSeverity.BLOCKER, message="err"
        )
        patches = [
            {"op": "replace", "path": "/number", "value": 99},
        ]
        with pytest.raises(UnsafePatchError):
            apply_patch_to_question(q, patches, issue)

    def test_digit_preserving_guard_triggers_on_digit_change(self):
        q = _make_sample_question()
        issue = Issue(
            id="i4", stage="s8", rule="lexicon", severity=IssueSeverity.WARNING, message="lex error"
        )
        # Change 343 to 350 on a lexicon issue
        patches = [
            {
                "op": "replace",
                "path": "/stem_text_en",
                "value": "Speed of sound is 350 m/s in air at 20 C.",
            },
        ]
        with pytest.raises(UnsafePatchError, match="Digit-preserving guard"):
            apply_patch_to_question(q, patches, issue)

    def test_patch_option_text(self):
        q = _make_sample_question()
        issue = Issue(
            id="i5", stage="s8", rule="text_layer", severity=IssueSeverity.BLOCKER, message="err"
        )
        patches = [
            {"op": "replace", "path": "/options/0/text_str_en", "value": "343 m/s (correct)"},
        ]
        patched = apply_patch_to_question(q, patches, issue)
        assert patched.options[0].text_str_en == "343 m/s (correct)"
