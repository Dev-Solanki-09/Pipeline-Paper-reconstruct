"""Minimal context builder for surgical LLM repair calls with hard token caps."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from examforge.ir.schema import Issue, Question

logger = logging.getLogger(__name__)


@dataclass
class RepairContext:
    """Minimal context slice provided to repair models."""

    issue_id: str
    rule: str
    question_number: int
    question_slice: dict[str, Any]
    profile_excerpt: dict[str, Any] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    crop_data: str | None = None
    estimated_tokens: int = 0


def _compact_question_slice(q: Question) -> dict[str, Any]:
    """Serialize a question into minimal compact JSON without nulls or internal block trees."""
    data: dict[str, Any] = {
        "num": q.number,
        "kind": q.kind.value if hasattr(q.kind, "value") else str(q.kind),
    }
    if q.section:
        data["section"] = q.section

    # Stems
    stem_txt = q.stem_text_en or q.stem_text_hi
    if stem_txt:
        data["stem"] = stem_txt.strip()

    # Options
    if q.options:
        data["opts"] = [
            {"lbl": opt.label, "txt": (opt.text_str_en or opt.text_str_hi).strip()}
            for opt in q.options
        ]

    # Bound answers if any
    if q.answer:
        ans_data: dict[str, Any] = {}
        if q.answer.correct_options:
            ans_data["opts"] = q.answer.correct_options
        if q.answer.numeric_value is not None:
            ans_data["val"] = q.answer.numeric_value
        if q.answer.numeric_range is not None:
            ans_data["rng"] = q.answer.numeric_range
        if ans_data:
            data["ans"] = ans_data

    return data


def build_repair_context(
    issue: Issue,
    question: Question,
    crop_data: str | None = None,
    profile_excerpt: dict[str, Any] | None = None,
    lessons: list[str] | None = None,
    max_tokens: int = 600,
) -> RepairContext:
    """
    Build a minimal context slice for a single question repair.

    Enforces hard token budget cap.
    """
    q_slice = _compact_question_slice(question)
    prof = profile_excerpt or {}
    lesson_list = list(lessons or [])

    # Initial token estimation
    payload = {
        "issue": issue.message,
        "q": q_slice,
        "prof": prof,
        "lessons": lesson_list,
    }
    raw_str = json.dumps(payload)
    est_tokens = len(raw_str) // 3 + 20

    # If exceeding max_tokens, perform surgical compaction
    if est_tokens > max_tokens:
        # 1. Drop lessons first
        lesson_list = []
        payload["lessons"] = []
        raw_str = json.dumps(payload)
        est_tokens = len(raw_str) // 3 + 20

    if est_tokens > max_tokens:
        # 2. Truncate stem text if very long
        stem = q_slice.get("stem", "")
        allowed_chars = max(100, (max_tokens - 80) * 3)
        if len(stem) > allowed_chars:
            q_slice["stem"] = stem[:allowed_chars] + "..."
        payload["q"] = q_slice
        raw_str = json.dumps(payload)
        est_tokens = len(raw_str) // 3 + 20

    return RepairContext(
        issue_id=issue.id,
        rule=issue.rule or "",
        question_number=question.number,
        question_slice=q_slice,
        profile_excerpt=prof,
        lessons=lesson_list,
        crop_data=crop_data,
        estimated_tokens=est_tokens,
    )
