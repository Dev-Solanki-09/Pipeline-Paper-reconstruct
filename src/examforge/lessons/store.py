"""
Phase 15.1 — Self-Improving Loop: Lessons Store.

Append-only lessons JSONL storage with file-locking, schema validation,
signature normalization, corrupt-line tolerance, and compaction.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LessonStatus = Literal["candidate", "promoted", "retired"]
LessonOutcome = Literal["validator-accepted", "human-accepted", "rejected"]


class ContextFeatures(BaseModel):
    """Contextual features associated with an issue occurrence."""

    profile_id: str = "generic"
    script: str = "Latn"
    kind: str = "mcq1"
    language: str = "en"


class Lesson(BaseModel):
    """A recorded lesson from an issue repair or human decision."""

    id: str = Field(default_factory=lambda: f"lsn_{uuid4().hex[:12]}")
    created: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    stage: str = "s7_repair"
    rule: str
    issue_signature: str
    context_features: ContextFeatures = Field(default_factory=ContextFeatures)
    fix_summary: str = ""
    fix_patch_template: dict[str, Any] = Field(default_factory=dict)
    outcome: LessonOutcome = "validator-accepted"
    count: int = 1
    last_seen: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    status: LessonStatus = "candidate"
    source_papers: list[str] = Field(default_factory=list)


def normalize_issue_signature(rule: str, token_pattern: str) -> str:
    """
    Produce a canonical signature for grouping equivalent issues:
    - Collapses whitespace
    - Replaces numeric literals with <NUM>
    - Replaces string constants with <STR>
    - Normalizes case for the rule prefix
    """
    cleaned_pattern = token_pattern.strip()
    cleaned_pattern = re.sub(r"\b\d+(\.\d+)?\b", "<NUM>", cleaned_pattern)
    cleaned_pattern = re.sub(r"['\"][^'\"]*['\"]", "<STR>", cleaned_pattern)
    cleaned_pattern = re.sub(r"\s+", " ", cleaned_pattern)
    return f"{rule.upper()}::{cleaned_pattern}"


class LessonsStore:
    """Thread-safe and process-safe append-only store for lessons."""

    def __init__(self, path: Path | str = "data/lessons/lessons.jsonl") -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(".lock")
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _acquire_lock(self):
        """Simple cross-platform file locking."""
        import time

        for _ in range(50):
            try:
                # Exclusive creation
                fd = self.lock_path.open("x")
                fd.close()
                return
            except FileExistsError:
                time.sleep(0.05)
        # Fallback: remove stale lock if older than 5 seconds
        try:
            if self.lock_path.exists() and (
                time.time() - self.lock_path.stat().st_mtime > 5.0
            ):
                self.lock_path.unlink(missing_ok=True)
                fd = self.lock_path.open("x")
                fd.close()
        except Exception:
            pass

    def _release_lock(self) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            self.lock_path.unlink(missing_ok=True)

    def record_lesson(
        self,
        rule: str,
        issue_signature: str,
        fix_patch_template: dict[str, Any],
        fix_summary: str = "",
        stage: str = "s7_repair",
        context_features: ContextFeatures | None = None,
        outcome: LessonOutcome = "validator-accepted",
        source_paper: str = "unknown",
    ) -> Lesson:
        """
        Record a new lesson or increment count/papers if identical signature & patch template exist.
        """
        self._acquire_lock()
        try:
            lessons = self._read_all_unlocked()
            matching_idx = -1
            patch_str = json.dumps(fix_patch_template, sort_keys=True)

            for i, lsn in enumerate(lessons):
                if (
                    lsn.rule == rule
                    and lsn.issue_signature == issue_signature
                    and json.dumps(lsn.fix_patch_template, sort_keys=True) == patch_str
                    and lsn.status != "retired"
                ):
                    matching_idx = i
                    break

            now_iso = datetime.now(UTC).isoformat()

            if matching_idx >= 0:
                lsn = lessons[matching_idx]
                lsn.count += 1
                lsn.last_seen = now_iso
                if source_paper and source_paper not in lsn.source_papers:
                    lsn.source_papers.append(source_paper)
                lessons[matching_idx] = lsn
                self._write_all_unlocked(lessons)
                return lsn

            # New lesson
            new_lsn = Lesson(
                rule=rule,
                issue_signature=issue_signature,
                fix_patch_template=fix_patch_template,
                fix_summary=fix_summary[:200],  # capped length
                stage=stage,
                context_features=context_features or ContextFeatures(),
                outcome=outcome,
                count=1,
                last_seen=now_iso,
                source_papers=[source_paper] if source_paper else [],
            )
            lessons.append(new_lsn)
            self._write_all_unlocked(lessons)
            return new_lsn
        finally:
            self._release_lock()

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        lessons = self.list_lessons()
        for lsn in lessons:
            if lsn.id == lesson_id:
                return lsn
        return None

    def list_lessons(
        self,
        status: LessonStatus | None = None,
        rule: str | None = None,
        min_count: int = 1,
    ) -> list[Lesson]:
        self._acquire_lock()
        try:
            lessons = self._read_all_unlocked()
            res = []
            for lsn in lessons:
                if status and lsn.status != status:
                    continue
                if rule and lsn.rule != rule:
                    continue
                if lsn.count < min_count:
                    continue
                res.append(lsn)
            return res
        finally:
            self._release_lock()

    def update_lesson_status(self, lesson_id: str, new_status: LessonStatus) -> bool:
        self._acquire_lock()
        try:
            lessons = self._read_all_unlocked()
            updated = False
            for i, lsn in enumerate(lessons):
                if lsn.id == lesson_id:
                    lsn.status = new_status
                    lessons[i] = lsn
                    updated = True
                    break
            if updated:
                self._write_all_unlocked(lessons)
            return updated
        finally:
            self._release_lock()

    def compact(self, max_records: int = 1000) -> int:
        """Compact duplicate signatures and prune retired lessons if exceeding max_records."""
        self._acquire_lock()
        try:
            lessons = self._read_all_unlocked()
            compacted: dict[str, Lesson] = {}
            for lsn in lessons:
                patch_key = json.dumps(lsn.fix_patch_template, sort_keys=True)
                key = (lsn.rule, lsn.issue_signature, patch_key)
                key_str = str(key)
                if key_str in compacted:
                    existing = compacted[key_str]
                    existing.count += lsn.count
                    for p in lsn.source_papers:
                        if p not in existing.source_papers:
                            existing.source_papers.append(p)
                    existing.last_seen = max(existing.last_seen, lsn.last_seen)
                else:
                    compacted[key_str] = lsn

            res_list = list(compacted.values())
            # If still over cap, prune oldest retired entries first
            if len(res_list) > max_records:
                non_retired = [item for item in res_list if item.status != "retired"]
                retired = [item for item in res_list if item.status == "retired"]
                retired.sort(key=lambda x: x.last_seen, reverse=True)
                allowed_retired = max(0, max_records - len(non_retired))
                res_list = non_retired + retired[:allowed_retired]

            self._write_all_unlocked(res_list)
            return len(res_list)
        finally:
            self._release_lock()

    def _read_all_unlocked(self) -> list[Lesson]:
        if not self.path.exists():
            return []
        lessons: list[Lesson] = []
        with open(self.path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    lessons.append(Lesson.model_validate(data))
                except Exception as e:
                    logger.warning(
                        "Corrupt lesson line %d skipped in %s: %s",
                        line_no,
                        self.path,
                        e,
                    )
        return lessons

    def _write_all_unlocked(self, lessons: list[Lesson]) -> None:
        lines = [lsn.model_dump_json() for lsn in lessons]
        content = "\n".join(lines) + ("\n" if lines else "")
        self.path.write_text(content, encoding="utf-8")
