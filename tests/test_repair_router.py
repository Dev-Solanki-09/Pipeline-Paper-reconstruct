"""Tests for repair router and escalation ladder."""

from __future__ import annotations

from examforge.ir.schema import Issue, IssueSeverity
from examforge.repair.router import RepairRouter, RepairTier


class TestRepairRouter:
    def test_default_ladder_routing(self):
        router = RepairRouter()
        issue = Issue(
            id="i1",
            stage="s8",
            rule="text_layer_agreement",
            severity=IssueSeverity.BLOCKER,
            message="test",
        )

        t0 = router.route(issue, attempt=0)
        assert t0 == RepairTier.T0

        t1 = router.route(issue, attempt=1)
        assert t1 == RepairTier.T1

        t2 = router.route(issue, attempt=2)
        assert t2 == RepairTier.T2

        t3 = router.route(issue, attempt=3)
        assert t3 == RepairTier.T3

        t4 = router.route(issue, attempt=4)
        assert t4 == RepairTier.T4

    def test_rule_specific_skipped_tiers(self):
        router = RepairRouter()
        # formulas skips T0 and T2
        issue = Issue(
            id="i2",
            stage="s8",
            rule="formulas",
            severity=IssueSeverity.BLOCKER,
            message="formula error",
        )

        assert router.route(issue, attempt=0) == RepairTier.T1
        assert router.route(issue, attempt=1) == RepairTier.T3
        assert router.route(issue, attempt=2) == RepairTier.T4

    def test_offline_mode_skips_models(self):
        router = RepairRouter()
        issue = Issue(
            id="i3", stage="s8", rule="lexicon", severity=IssueSeverity.WARNING, message="lex error"
        )

        # In offline mode, T2 and T3 are excluded
        assert router.route(issue, attempt=0, offline_mode=True) == RepairTier.T0
        assert router.route(issue, attempt=1, offline_mode=True) == RepairTier.T4

    def test_budget_exhausted_escalates_to_human_review(self):
        router = RepairRouter()
        issue = Issue(
            id="i4",
            stage="s8",
            rule="text_layer_agreement",
            severity=IssueSeverity.BLOCKER,
            message="err",
        )

        # When budget is exhausted, immediately routes to T4
        assert router.route(issue, attempt=0, budget_exhausted=True) == RepairTier.T4
