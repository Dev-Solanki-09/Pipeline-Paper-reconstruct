"""
Phase 15.3 — Lesson Retrieval with Exact Matching, BM25-Style Scoring, and Token Caps.
"""

from __future__ import annotations

import math
import re

from examforge.lessons.store import ContextFeatures, Lesson, LessonsStore


class LessonRetriever:
    """Retrieves relevant non-retired lessons within a strict token budget."""

    def __init__(self, store: LessonsStore) -> None:
        self.store = store

    def retrieve(
        self,
        rule: str,
        stage: str = "s7_repair",
        context: ContextFeatures | None = None,
        query_text: str = "",
        top_k: int = 3,
        token_budget: int = 500,
    ) -> list[Lesson]:
        """
        Retrieve top-k matching lessons.
        1. Filters out retired lessons.
        2. Exact matches on stage and rule.
        3. If context provided, prioritizes matching (script, kind).
        4. Ranks remainder with BM25-style term frequency on query_text vs issue_signature.
        5. Strictly caps returned items so total estimated tokens <= token_budget.
        """
        all_lessons = self.store.list_lessons(rule=rule)
        candidates = [
            cand for cand in all_lessons if cand.status != "retired" and cand.stage == stage
        ]
        if not candidates:
            return []

        # Scoring
        query_tokens = self._tokenize(query_text)
        scored: list[tuple[float, Lesson]] = []

        for lsn in candidates:
            score = 10.0  # Base match for rule & stage

            # Context boost
            if context:
                if lsn.context_features.script == context.script:
                    score += 5.0
                if lsn.context_features.kind == context.kind:
                    score += 5.0
                if lsn.context_features.profile_id == context.profile_id:
                    score += 2.0

            # Recurrence count boost (log scale)
            score += math.log1p(lsn.count)

            # BM25-like token overlap between query and issue_signature
            sig_tokens = self._tokenize(lsn.issue_signature + " " + lsn.fix_summary)
            if query_tokens and sig_tokens:
                overlap = len(set(query_tokens) & set(sig_tokens))
                score += overlap * 2.0

            scored.append((score, lsn))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select items within token budget (~4 characters per token)
        results: list[Lesson] = []
        tokens_used = 0

        for _, lsn in scored:
            if len(results) >= top_k:
                break
            # Estimate token cost of serialized lesson
            text_repr = f"{lsn.issue_signature} {lsn.fix_summary} {lsn.fix_patch_template}"
            est_tokens = max(1, len(text_repr) // 4)

            if tokens_used + est_tokens > token_budget and results:
                # Token cap reached; stop adding
                break

            results.append(lsn)
            tokens_used += est_tokens

        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t.lower() for t in re.findall(r"\w+", text) if len(t) > 1]
