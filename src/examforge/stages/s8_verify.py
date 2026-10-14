"""
S8 Verify: Specification Rule Enforcement & Quality Verification (Phase O4).

Evaluates the reconstructed ExamDocument against the frozen Spec,
running active validators partitioned across CostTiers (Free, IO, Heavy)
and supporting scoped incremental re-verification of patched questions.
"""

from __future__ import annotations

import logging
from typing import Optional

from examforge.ir.schema import ExamDocument, Issue, IssueSeverity
from examforge.spec import Spec
from examforge.stages.base import Stage, StageContext, StageResult
import examforge.validators  # noqa: F401
from examforge.validators.base import CostTier
from examforge.validators.registry import (
    get_canonical_validator_name,
    get_validator,
    get_validator_tier,
)

logger = logging.getLogger(__name__)


def verify_question(
    document: ExamDocument,
    question_id: str,
    spec: Spec | None = None,
    cost_tiers: set[CostTier] | None = None,
) -> list[Issue]:
    """
    O4.3: Scoped incremental verification.
    After a repair, re-runs only validators relevant to the target question.
    """
    spec = spec or Spec.default(verifiers_v2=True)
    target_tiers = cost_tiers or {CostTier.FREE, CostTier.IO}
    issues: list[Issue] = []

    # Find target question
    target_q = next((q for q in document.questions if q.id == question_id), None)
    if not target_q:
        return issues

    # Create shallow document containing only the target question
    scoped_doc = document.model_copy(update={"questions": [target_q]})

    for rule_id, rule in spec.rules.items():
        check_name = rule.check or rule_id
        tier = get_validator_tier(check_name)
        if tier not in target_tiers:
            continue

        validator = get_validator(check_name)
        if not validator:
            continue

        rule_issues = validator(scoped_doc, rule)
        for issue in rule_issues:
            if (
                issue.question_id == question_id
                or issue.element_id == question_id
                or (issue.id and f"_{question_id}" in issue.id)
            ):
                if not issue.question_id:
                    issue.question_id = question_id
                issues.append(issue)

    return issues


class S8Verify(Stage):
    """
    Stage 8: Run spec rule validators partitioned by cost tiers.
    """

    name = "s8_verify"

    @classmethod
    def capabilities(cls) -> list[str]:
        return ["validators", "cost_tiers", "incremental_verify"]

    def validate_preconditions(self, ctx: StageContext) -> list[str]:
        """S8 requires at least pages to be populated."""
        violations = []
        if not ctx.document.pages:
            violations.append("No pages found in document — S0 Intake must run first.")
        return violations

    def run(
        self,
        ctx: StageContext,
        allowed_cost_tiers: set[CostTier] | None = None,
    ) -> StageResult:
        doc = ctx.document
        spec = ctx.spec or Spec.default()
        issues: list[Issue] = []
        metrics: dict = {}

        # O4.1 Cost Tiers gating
        if allowed_cost_tiers is None:
            if ctx.config and getattr(ctx.config, "fast_validators_only", False):
                allowed_cost_tiers = {CostTier.FREE, CostTier.IO}
            elif ctx.config and getattr(ctx.config, "skip_heavy_validators", False):
                allowed_cost_tiers = {CostTier.FREE, CostTier.IO}
            else:
                allowed_cost_tiers = {CostTier.FREE, CostTier.IO, CostTier.HEAVY}

        rules_evaluated = 0
        validators_matched = 0
        tiers_skipped = 0

        # O4.5 Capability / profile gating: check if document/profile is bilingual
        is_bilingual = any(b.lang.value == "hi" for b in doc.blocks) or any(
            bool(q.stem_text_hi) for q in doc.questions
        )
        if ctx.resolved_profile and hasattr(ctx.resolved_profile, "languages"):
            if "hi" in ctx.resolved_profile.languages:
                is_bilingual = True

        for rule_id, rule in spec.rules.items():
            check_name = rule.check or rule_id
            canonical_name = get_canonical_validator_name(check_name)
            tier = get_validator_tier(check_name)

            # Cost tier gate
            if tier not in allowed_cost_tiers:
                tiers_skipped += 1
                continue

            # O4.5 Capability gate: skip bilingual rule on monolingual documents
            if canonical_name == "language_consistency" and not is_bilingual:
                continue

            rules_evaluated += 1
            validator = get_validator(check_name)
            if not validator:
                logger.debug("No validator found for rule %s (check: %s)", rule_id, rule.check)
                continue

            validators_matched += 1
            rule_issues = validator(doc, rule)
            issues.extend(rule_issues)

        # Merge new issues into document
        doc.issues.extend(issues)

        # 5.8 Issue stream: write all issues to issues.jsonl for downstream consumption
        if ctx.run_dir and ctx.run_dir.exists():
            issues_file = ctx.run_dir / "issues.jsonl"
            try:
                with open(issues_file, "w", encoding="utf-8") as f:
                    for issue in doc.issues:
                        f.write(issue.model_dump_json() + "\n")
            except Exception as e:
                logger.warning("Failed to write issues.jsonl: %s", e)

        self._fail_fast = getattr(ctx.config, "fail_fast", False) if ctx.config else False

        blockers = sum(1 for i in issues if i.severity == IssueSeverity.BLOCKER)
        warnings = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        rule_breakdown: dict[str, int] = {}
        for i in issues:
            rule_breakdown[i.rule] = rule_breakdown.get(i.rule, 0) + 1

        metrics.update({
            "rules_evaluated": rules_evaluated,
            "validators_matched": validators_matched,
            "tiers_skipped": tiers_skipped,
            "new_issues": len(issues),
            "total_issues": len(doc.issues),
            "blockers": blockers,
            "warnings": warnings,
            "rule_breakdown": rule_breakdown,
        })

        logger.info(
            "  S8 Verify complete: evaluated %d rules, found %d issues (%d blockers, %d warnings, %d tier-skipped)",
            rules_evaluated,
            len(issues),
            blockers,
            warnings,
            tiers_skipped,
        )

        return StageResult(document=doc, metrics=metrics, issues=issues)

    def validate_postconditions(self, result: StageResult) -> list[str]:
        """Check postconditions based on fail policy."""
        violations = []
        blockers = sum(1 for i in result.issues if i.severity == IssueSeverity.BLOCKER)
        fail_fast = getattr(self, "_fail_fast", False)
        if blockers > 0 and fail_fast:
            violations.append(f"Verification found {blockers} blocker issues under fail_fast policy.")
        return violations
