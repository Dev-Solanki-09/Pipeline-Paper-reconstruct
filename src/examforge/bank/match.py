"""Strict Question Bank matching with zero false-reuse guarantee (Phase 12.3)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from examforge.bank.fingerprint import (
    compute_number_signature,
    compute_simhash_64,
    hamming_distance_64,
    normalize_text_for_fingerprint,
)
from examforge.bank.store import BankQuestionRecord, QuestionBankStore
from examforge.ir.schema import Question

logger = logging.getLogger(__name__)


class MatchKind(StrEnum):
    """Classification of Question Bank match results."""

    EXACT_REUSE = "exact_reuse"  # Safe for exact 0-token reuse
    NEAR_HINT = "near_hint"  # Unverified similarity, repair hint only
    NO_MATCH = "no_match"  # No similar question found in bank


@dataclass
class MatchResult:
    """Detailed matching result with audit evidence."""

    kind: MatchKind
    matched_record: BankQuestionRecord | None = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


class QuestionBankMatcher:
    """
    Evaluates questions against verified bank records with safety gates.

    Strict Invariant:
    Any difference in numerals, units, or option count strictly blocks
    EXACT_REUSE to prevent false reuse of modified exam questions.
    """

    def __init__(
        self,
        store: QuestionBankStore,
        hamming_threshold: int = 8,
    ) -> None:
        self.store = store
        self.hamming_threshold = hamming_threshold

    def match(
        self,
        question: Question,
        exam_family: str | None = None,
    ) -> MatchResult:
        """Find matching record for question with multi-stage verification."""
        q_stem = question.stem_text_en or question.stem_text_hi or ""
        q_simhash = compute_simhash_64(q_stem)
        q_sig = compute_number_signature(question)

        candidates = self.store.find_candidates(exam_family=exam_family, limit=200)
        if not candidates and exam_family is not None:
            candidates = self.store.find_candidates(exam_family=None, limit=200)
        if not candidates:
            return MatchResult(kind=MatchKind.NO_MATCH)

        best_cand: BankQuestionRecord | None = None
        best_dist = 65

        for cand in candidates:
            dist = hamming_distance_64(cand.simhash, q_simhash)
            if dist < best_dist:
                best_dist = dist
                best_cand = cand

            # Evaluate candidate against strict gate
            if dist <= self.hamming_threshold:
                # 1. Strict number signature check
                if cand.number_signature != q_sig:
                    # Digit/unit difference strictly blocks EXACT_REUSE!
                    continue

                # 2. Strict option content verification
                try:
                    cand_ir = json.loads(cand.ir_json)
                    cand_opts = cand_ir.get("options", [])
                except Exception:
                    continue

                if len(cand_opts) != len(question.options):
                    continue

                opts_match = True
                for c_opt, q_opt in zip(cand_opts, question.options, strict=False):
                    c_txt = normalize_text_for_fingerprint(
                        c_opt.get("text_str_en") or c_opt.get("text_str_hi") or ""
                    )
                    q_txt = normalize_text_for_fingerprint(
                        q_opt.text_str_en or q_opt.text_str_hi or ""
                    )
                    if c_txt != q_txt:
                        opts_match = False
                        break

                if opts_match:
                    logger.info(
                        "QuestionBank exact reuse: content_hash=%s (dist=%d)",
                        cand.content_hash,
                        dist,
                    )
                    return MatchResult(
                        kind=MatchKind.EXACT_REUSE,
                        matched_record=cand,
                        confidence=1.0 - (dist / 64.0),
                        evidence={
                            "content_hash": cand.content_hash,
                            "hamming_dist": dist,
                            "signature_matched": True,
                        },
                    )

        # Check if near hint applies
        if best_cand and best_dist <= self.hamming_threshold:
            return MatchResult(
                kind=MatchKind.NEAR_HINT,
                matched_record=best_cand,
                confidence=max(0.0, 1.0 - (best_dist / 64.0)),
                evidence={
                    "content_hash": best_cand.content_hash,
                    "hamming_dist": best_dist,
                    "reason": "signature_mismatch_or_minor_difference",
                },
            )

        return MatchResult(kind=MatchKind.NO_MATCH)
