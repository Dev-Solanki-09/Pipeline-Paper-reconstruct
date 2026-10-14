"""
Stage 7: Escalation Ladder & Repair (S7) — Phase O5.

Performs surgical repairs for validated issues using an escalation ladder:
- T0: Deterministic fix (gap re-search, lexicon)
- T1: Local re-parse / second opinion
- T2: Cheap VLM candidate chooser
- T3: Strong model constrained JSON patch with digit-preserving guard
- T4: Human review escalation (exit code 20, review.html)

Enforces:
- O5.1: Net-benefit ledger tracking validators before/after, accept/revert, auto-disabling harmful tiers
- O5.2: LLM-eligible issues only (BLOCKER + localized bounds + candidates/text), per-paper cap
- O5.3: Preference for local tiers (T0/T1)
- O5.4: Per-paper token budget enforcement
- O5.5: Repair harm rate <= 0.1% and patch safety guards
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity, Question
from examforge.llm.types import LLMRequest, Message
from examforge.repair.context import build_repair_context
from examforge.repair.gap_search import gap_search_recover_question
from examforge.repair.ledger import NetBenefitLedger, RepairAttemptRecord
from examforge.repair.patch import apply_patch_to_question
from examforge.repair.router import RepairRouter, RepairTier, is_llm_eligible
from examforge.stages.base import Stage, StageContext, StageResult
from examforge.stages.s8_verify import verify_question

logger = logging.getLogger(__name__)


class S7Repair(Stage):
    """Stage 7: Autonomous issue repair and escalation ladder."""

    name = "s7_repair"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["repair", "escalation", "offline_fallback", "net_benefit_ledger", "token_guardrails"]

    def run(self, ctx: StageContext) -> StageResult:
        doc = ctx.document

        # 1. Check feature flag rollback
        use_s7 = (
            ctx.config.flag("s7_repair", default=False)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else False
        )
        if not use_s7:
            return StageResult(
                document=doc,
                metrics={"s7_repair_skipped": True},
                issues=doc.issues,
            )

        # 2. If no issues, pass through
        if not doc.issues:
            return StageResult(
                document=doc,
                metrics={"repaired_count": 0},
                issues=[],
            )

        ctx.stage_dir.mkdir(parents=True, exist_ok=True)
        if ctx.run_dir:
            ctx.run_dir.mkdir(parents=True, exist_ok=True)

        ledger = NetBenefitLedger(run_dir=ctx.run_dir)
        router = RepairRouter()
        llm_client = getattr(ctx, "llm_client", None)
        is_offline = llm_client is None or getattr(ctx.config, "offline", False)

        use_lessons = (
            ctx.config.flag("lessons", default=False)
            if (ctx.config and hasattr(ctx.config, "flag"))
            else False
        )
        lessons_store = None
        lesson_retriever = None
        if use_lessons:
            from examforge.lessons import LessonRetriever, LessonsStore
            lessons_path = getattr(ctx.config, "lessons_path", "data/lessons/lessons.jsonl")
            lessons_store = LessonsStore(lessons_path)
            lesson_retriever = LessonRetriever(lessons_store)

        # O5.2 / O5.4: Per-paper caps and token budget
        max_llm_repairs = getattr(ctx.config, "max_llm_repairs", 10) if ctx.config else 10
        llm_repairs_count = 0
        token_budget = getattr(ctx.config, "token_budget", None) if ctx.config else None
        if token_budget is None and ctx.resolved_profile and hasattr(ctx.resolved_profile, "compute"):
            token_budget = getattr(ctx.resolved_profile.compute, "token_budget", 5000)
        if token_budget is None:
            token_budget = 5000
        tokens_spent = 0
        budget_exhausted = False

        remaining_issues = list(doc.issues)
        resolved_issues: list[Issue] = []
        repaired_count = 0
        needs_review = False

        for issue in list(remaining_issues):
            # O4.4 / O5.2: WARN never triggers repair; only BLOCKER issues are repair-eligible
            if issue.severity != IssueSeverity.BLOCKER:
                continue

            # Find target question (can be None for sequence_gaps where question is missing)
            q = _find_question_for_issue(doc, issue)
            if not q and issue.rule not in ("sequence_gaps", "numbering_continuity"):
                continue

            attempt = 0
            resolved = False
            prof_id = ctx.resolved_profile.id if ctx.resolved_profile else "generic"

            # Pre-repair validators status on target question
            if q:
                pre_issues = verify_question(doc, q.id)
                blockers_before = sum(1 for i in pre_issues if i.severity == IssueSeverity.BLOCKER)
                orig_q = q.model_copy(deep=True)
            else:
                pre_issues = []
                blockers_before = 1
                orig_q = None

            while attempt < 5 and not resolved:
                # O5.1 Auto-disable tiers with non-positive net benefit
                disabled_tiers = {
                    t for t in (RepairTier.T0, RepairTier.T1, RepairTier.T2, RepairTier.T3)
                    if ledger.is_tier_disabled(issue.rule or "unknown", t.value)
                }

                tier = router.route(
                    issue,
                    attempt=attempt,
                    offline_mode=is_offline,
                    budget_exhausted=budget_exhausted,
                    disabled_tiers=disabled_tiers,
                )

                attempt_tokens = 0
                attempt_patches: list[dict[str, Any]] = []
                patch_applied = False
                revert_reason = None

                # T0: Deterministic sequence gaps recovery
                if tier == RepairTier.T0 and issue.rule in ("sequence_gaps", "numbering_continuity"):
                    missing_nums = (issue.evidence or {}).get("missing_questions", [])
                    for m_num in missing_nums:
                        rec_q = gap_search_recover_question(doc, m_num)
                        if rec_q:
                            doc.questions.append(rec_q)
                            doc.questions.sort(key=lambda x: x.number)
                            patch_applied = True
                            q = rec_q
                            orig_q = rec_q.model_copy(deep=True)
                            break

                # Attempt zero-token lesson reuse if lessons enabled
                if use_lessons and lesson_retriever and not patch_applied:
                    from examforge.lessons import ContextFeatures
                    matching_lessons = lesson_retriever.retrieve(
                        rule=issue.rule or "unknown",
                        context=ContextFeatures(
                            profile_id=prof_id,
                            kind=str(q.kind),
                        ),
                        query_text=issue.message or "",
                    )
                    for lsn in matching_lessons:
                        cand_patches = lsn.fix_patch_template.get("patches", [])
                        if cand_patches:
                            try:
                                patched_q = apply_patch_to_question(q, cand_patches, issue, doc)
                                for idx, qu in enumerate(doc.questions):
                                    if qu.id == q.id:
                                        doc.questions[idx] = patched_q
                                        q = patched_q
                                        break
                                patch_applied = True
                                attempt_patches = cand_patches
                                logger.info("Zero-token repair applied from lesson %s", lsn.id)
                                break
                            except Exception as e:
                                revert_reason = str(e)

                # O5.2 / O5.3: Model-assisted tiers (T2 / T3)
                can_llm_repair = (
                    not patch_applied
                    and tier in (RepairTier.T2, RepairTier.T3)
                    and not is_offline
                    and llm_client
                    and not budget_exhausted
                )
                if can_llm_repair:
                    # O5.2 Eligibility check
                    eligible, reason = is_llm_eligible(issue, q)
                    if not eligible:
                        logger.debug("Issue %s ineligible for LLM repair: %s", issue.id, reason)
                        tier = RepairTier.T4
                        can_llm_repair = False
                    elif llm_repairs_count >= max_llm_repairs:
                        logger.warning("Per-paper LLM repair cap reached (%d)", max_llm_repairs)
                        tier = RepairTier.T4
                        can_llm_repair = False

                if can_llm_repair:
                    try:
                        repair_ctx = build_repair_context(issue, q)
                        req = LLMRequest(
                            stage_name="s7_repair",
                            question_no=q.number,
                            messages=[
                                Message(
                                    role="system",
                                    content="Repair issue via RFC 6902 JSON patches.",
                                ),
                                Message(role="user", content=json.dumps(repair_ctx.question_slice)),
                            ],
                        )
                        resp = llm_client.complete(req)
                        used_tok = getattr(getattr(resp, "usage", None), "total_tokens", 50) or 50
                        attempt_tokens = used_tok
                        tokens_spent += used_tok
                        llm_repairs_count += 1

                        if tokens_spent >= token_budget:
                            budget_exhausted = True
                            needs_review = True

                        raw_json = json.loads(resp.content)
                        patches = raw_json.get("patches", [])
                        if patches:
                            patched_q = apply_patch_to_question(q, patches, issue, doc)
                            for idx, qu in enumerate(doc.questions):
                                if qu.id == q.id:
                                    doc.questions[idx] = patched_q
                                    q = patched_q
                                    break
                            patch_applied = True
                            attempt_patches = patches
                    except Exception as e:
                        revert_reason = str(e)
                        logger.debug("T2/T3 repair error: %s", e)

                if tier == RepairTier.T4:
                    needs_review = True
                    break

                # Post-repair validation & net-benefit ledger accounting
                if patch_applied:
                    post_issues = verify_question(doc, q.id)
                    blockers_after = sum(1 for i in post_issues if i.severity == IssueSeverity.BLOCKER)
                    net_benefit = blockers_before - blockers_after

                    # Target issue must be resolved
                    target_still_present = any(
                        (i.id == issue.id or (i.rule == issue.rule and i.severity == IssueSeverity.BLOCKER))
                        for i in post_issues
                    )
                    new_blocker_introduced = blockers_after > blockers_before

                    if target_still_present or new_blocker_introduced:
                        # Revert question to pre-repair state
                        for idx, qu in enumerate(doc.questions):
                            if qu.id == orig_q.id:
                                doc.questions[idx] = orig_q.model_copy(deep=True)
                                q = doc.questions[idx]
                                break
                        revert_msg = (
                            "Target issue not resolved"
                            if target_still_present
                            else "Patch introduced new blocker"
                        )
                        ledger.record_attempt(
                            RepairAttemptRecord(
                                paper_id=doc.source_hash or doc.source_path or "paper",
                                question_id=q.id,
                                rule=issue.rule or "unknown",
                                issue_id=issue.id,
                                tier=tier.value,
                                validators_before=[i.id for i in pre_issues],
                                validators_after=[i.id for i in post_issues],
                                blockers_before=blockers_before,
                                blockers_after=blockers_after,
                                net_benefit=net_benefit,
                                status="reverted",
                                revert_reason=revert_msg,
                                tokens_used=attempt_tokens,
                            )
                        )
                    else:
                        resolved = True
                        repaired_count += 1
                        resolved_issues.append(issue)
                        ledger.record_attempt(
                            RepairAttemptRecord(
                                paper_id=doc.source_hash or doc.source_path or "paper",
                                question_id=q.id,
                                rule=issue.rule or "unknown",
                                issue_id=issue.id,
                                tier=tier.value,
                                validators_before=[i.id for i in pre_issues],
                                validators_after=[i.id for i in post_issues],
                                blockers_before=blockers_before,
                                blockers_after=blockers_after,
                                net_benefit=net_benefit,
                                status="accepted",
                                tokens_used=attempt_tokens,
                            )
                        )

                        # Record lesson if lessons enabled
                        if use_lessons and lessons_store and attempt_patches:
                            from examforge.lessons import (
                                ContextFeatures,
                                normalize_issue_signature,
                            )
                            sig = normalize_issue_signature(
                                issue.rule or "unknown", issue.message or ""
                            )
                            lessons_store.record_lesson(
                                rule=issue.rule or "unknown",
                                issue_signature=sig,
                                fix_patch_template={"patches": attempt_patches},
                                fix_summary=f"Repaired {issue.id} on Q{q.number}",
                                stage="s7_repair",
                                context_features=ContextFeatures(
                                    profile_id=prof_id,
                                    kind=str(q.kind),
                                ),
                                outcome="validator-accepted",
                                source_paper=doc.source_hash or doc.source_path or "paper",
                            )
                        break
                elif revert_reason:
                    ledger.record_attempt(
                        RepairAttemptRecord(
                            paper_id=doc.source_hash or doc.source_path or "paper",
                            question_id=q.id,
                            rule=issue.rule or "unknown",
                            issue_id=issue.id,
                            tier=tier.value,
                            status="reverted",
                            revert_reason=revert_reason,
                            tokens_used=attempt_tokens,
                        )
                    )

                attempt += 1

        for iss in resolved_issues:
            if iss in remaining_issues:
                remaining_issues.remove(iss)
        doc.issues = remaining_issues

        metrics: dict[str, Any] = {"repaired_count": repaired_count}
        metrics.update(ledger.summary())
        metrics["tokens_spent"] = tokens_spent
        metrics["llm_repairs_count"] = llm_repairs_count
        metrics["budget_exhausted"] = budget_exhausted

        if needs_review or budget_exhausted or (is_offline and len(remaining_issues) > 0):
            metrics["needs_review"] = True
            metrics["exit_code"] = 20
            _generate_review_html(doc, remaining_issues, ctx.stage_dir)
            if ctx.run_dir:
                _generate_review_html(doc, remaining_issues, ctx.run_dir)

        return StageResult(
            document=doc,
            metrics=metrics,
            issues=remaining_issues,
        )


def _find_question_for_issue(doc: ExamDocument, issue: Issue) -> Question | None:
    """Find question associated with an issue from evidence, question_id, or ID."""
    if issue.question_id:
        for q in doc.questions:
            if q.id == issue.question_id:
                return q

    ev = issue.evidence or {}
    q_num = ev.get("question_number")
    if q_num is not None:
        for q in doc.questions:
            if q.number == q_num:
                return q

    # Match from ID string
    for q in doc.questions:
        if f"q{q.number}" in issue.id or f"q_{q.number}" in issue.id or f"_{q.id}" in issue.id:
            return q
    return None


def _generate_review_html(doc: ExamDocument, issues: list[Issue], out_dir: Path) -> None:
    """Generate human review HTML report when model escalation reaches T4."""
    html_lines = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Human Review Required (Exit Code 20)</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; padding: 20px; background: #fdfdfd; }",
        ".header { border-bottom: 2px solid #e11d48; padding-bottom: 10px; margin-bottom: 20px; }",
        (
            ".issue-card { background: white; border: 1px solid #e2e8f0; "
            "border-radius: 6px; padding: 16px; margin-bottom: 12px; }"
        ),
        (
            ".badge { display: inline-block; padding: 2px 8px; border-radius: 4px; "
            "font-size: 12px; font-weight: bold; background: #fee2e2; color: #991b1b; }"
        ),
        "</style></head><body>",
        "<div class='header'>",
        "  <h1>Human Review Required (Exit Code 20)</h1>",
        f"  <p>Source: {doc.source_path} — {len(issues)} unresolved issue(s)</p>",
        "</div>",
    ]

    for iss in issues:
        html_lines.append("<div class='issue-card'>")
        html_lines.append(f"  <span class='badge'>{iss.severity.value.upper()}</span>")
        html_lines.append(f"  <h3>Rule: {iss.rule} ({iss.id})</h3>")
        html_lines.append(f"  <p>{iss.message}</p>")
        if iss.evidence:
            html_lines.append(f"  <pre>{json.dumps(iss.evidence, indent=2)}</pre>")
        html_lines.append("</div>")

    html_lines.append("</body></html>")
    (out_dir / "review.html").write_text("\n".join(html_lines), encoding="utf-8")
