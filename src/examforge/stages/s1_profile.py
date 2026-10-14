"""
Stage S1: Profile Resolution & Auto-Profiling (Phase 13).

Resolves the exam profile for the document.
If `autoprofile` flag is enabled (or `--profile auto`), fingerprints the document,
checks profile_cache.sqlite, and infers/completes a profile if un-cached.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from examforge.ir.schema import Issue, IssueSeverity
from examforge.profiles.fingerprint import ProfileCache, extract_document_fingerprint
from examforge.profiles.infer_llm import complete_profile_llm
from examforge.profiles.infer_rules import infer_profile_deterministic
from examforge.profiles.schema import ExamProfile
from examforge.stages.base import Stage, StageContext, StageResult

logger = logging.getLogger(__name__)


class S1Profile(Stage):
    """Stage S1: Profile Resolution and Auto-Profiling."""

    name = "s1_profile"

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        violations = []
        if not ctx.document.pages and not ctx.document.blocks:
            violations.append("S1 Profile requires pages or blocks in document.")
        return violations

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document
        issues: list[Issue] = []
        metrics: dict[str, Any] = {}

        use_autoprofile = (
            ctx.config.flag("autoprofile", default=False)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else False
        )

        if not use_autoprofile:
            # Traditional path: resolved profile from CLI or spec
            prof = ctx.resolved_profile
            doc.metadata.exam_name = getattr(prof, "id", None)
            metrics["profile"] = getattr(prof, "id", "default")
            metrics["autoprofiled"] = False
            return StageResult(document=doc, metrics=metrics, issues=issues)

        # Autoprofile path:
        cache_path = getattr(
            ctx.config, "profile_cache_path", Path("data/profiles/profile_cache.sqlite")
        )
        cache = ProfileCache(cache_path)

        fp = extract_document_fingerprint(doc)
        metrics["fingerprint_hash"] = fp.doc_hash

        cached = cache.lookup(fp.doc_hash)
        if cached:
            p_id, p_yaml, conf, hits = cached
            cache.record_hit(fp.doc_hash)
            profile_dict = yaml.safe_load(p_yaml)
            prof = ExamProfile.model_validate(profile_dict)
            ctx.profile = prof
            doc.metadata.exam_name = prof.id
            metrics["profile"] = prof.id
            metrics["autoprofiled"] = True
            metrics["cache_hit"] = True
            metrics["confidence"] = conf
            metrics["hit_count"] = hits + 1
            logger.info(
                "  S1 Profile: Cache hit for fingerprint %s -> %s", fp.doc_hash[:8], prof.id
            )
            return StageResult(document=doc, metrics=metrics, issues=issues)

        # Cache miss -> Deterministic Inference
        infer_res = infer_profile_deterministic(doc, fp)
        prof = infer_res.profile
        confidence = infer_res.overall_confidence
        needs_review = bool(infer_res.low_confidence_fields)

        # Check if LLM completion is needed
        if (
            infer_res.low_confidence_fields
            and getattr(ctx.config, "agent", None)
            and ctx.config.agent.enabled
        ):
            llm_client = getattr(ctx, "llm_client", None)
            if llm_client:
                prof, needs_review = complete_profile_llm(infer_res, doc, llm_client)

        ctx.profile = prof
        doc.metadata.exam_name = prof.id

        # Persist to cache
        cache.store(
            fingerprint_hash=fp.doc_hash,
            profile_id=prof.id,
            profile_yaml=yaml.dump(prof.model_dump(), sort_keys=False, allow_unicode=True),
            confidence=confidence,
        )

        if needs_review:
            issues.append(
                Issue(
                    id=f"autoprofile_needs_review_{fp.doc_hash[:8]}",
                    stage="s1_profile",
                    rule="autoprofile",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Auto-profile {prof.id} has low-confidence fields: "
                        f"{', '.join(infer_res.low_confidence_fields)}"
                    ),
                )
            )

        metrics["profile"] = prof.id
        metrics["autoprofiled"] = True
        metrics["cache_hit"] = False
        metrics["confidence"] = confidence
        metrics["needs_review"] = needs_review

        logger.info(
            "  S1 Profile: Inferred profile %s (confidence=%.2f, needs_review=%s)",
            prof.id,
            confidence,
            needs_review,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        return []
