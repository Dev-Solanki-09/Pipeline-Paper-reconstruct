"""
Repair Net-Benefit Ledger (Phase O5.1 & O5.5).

Tracks all repair attempts, validator status before and after, accept/revert
decisions, and net-benefit delta. Automatically disables tiers or issue types
that show zero or negative net benefit, and measures the repair harm rate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class RepairAttemptRecord:
    """Record of a single surgical repair attempt."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    paper_id: str = "paper"
    question_id: str = "q"
    rule: str = "unknown"
    issue_id: str = "issue"
    tier: str = "T0"  # T0, T1, T2, T3, T4
    validators_before: list[str] = field(default_factory=list)
    validators_after: list[str] = field(default_factory=list)
    blockers_before: int = 0
    blockers_after: int = 0
    net_benefit: int = 0  # blockers_before - blockers_after
    status: Literal["accepted", "reverted", "failed", "skipped"] = "accepted"
    revert_reason: str | None = None
    tokens_used: int = 0
    gt_delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NetBenefitLedger:
    """
    In-memory and file-backed ledger tracking repair efficacy across issues and tiers.
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        self.run_dir = run_dir
        self.records: list[RepairAttemptRecord] = []
        # Cumulative benefit map: (rule, tier) -> int
        self._cumulative_benefit: dict[tuple[str, str], int] = {}
        # Count of attempts per (rule, tier)
        self._attempt_counts: dict[tuple[str, str], int] = {}

    def record_attempt(self, record: RepairAttemptRecord) -> None:
        """Add a repair attempt record and update cumulative statistics."""
        self.records.append(record)
        key = (record.rule, record.tier)
        self._attempt_counts[key] = self._attempt_counts.get(key, 0) + 1
        self._cumulative_benefit[key] = self._cumulative_benefit.get(key, 0) + record.net_benefit

        logger.debug(
            "Repair ledger entry: rule=%s tier=%s status=%s net_benefit=%d (cumulative=%d)",
            record.rule,
            record.tier,
            record.status,
            record.net_benefit,
            self._cumulative_benefit[key],
        )

        if self.run_dir and self.run_dir.exists():
            self._append_to_file(record)

    def _append_to_file(self, record: RepairAttemptRecord) -> None:
        ledger_file = self.run_dir / "repair_ledger.jsonl"
        try:
            with open(ledger_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
        except Exception as e:
            logger.warning("Failed to write to repair_ledger.jsonl: %s", e)

    def is_tier_disabled(self, rule: str, tier: str, min_attempts: int = 2) -> bool:
        """
        O5.1: Auto-disable tiers or issue types with zero or negative net benefit
        after a minimum number of attempts.
        """
        key = (rule, tier)
        attempts = self._attempt_counts.get(key, 0)
        if attempts < min_attempts:
            return False
        benefit = self._cumulative_benefit.get(key, 0)
        return benefit <= 0

    def repair_harm_rate(self) -> float:
        """
        O5.5: Share of repairs that caused harm (net_benefit < 0 or reverted due to corruption).
        """
        if not self.records:
            return 0.0
        # A repair caused harm if it increased blockers or was reverted for introducing blockers/guard errors
        harmful = sum(
            1
            for r in self.records
            if r.net_benefit < 0
            or (r.status == "reverted" and r.revert_reason and "introduced" in r.revert_reason.lower())
        )
        return harmful / len(self.records)

    def total_tokens(self) -> int:
        """Total tokens expended during repairs."""
        return sum(r.tokens_used for r in self.records)

    def accepted_count(self) -> int:
        """Count of accepted repairs."""
        return sum(1 for r in self.records if r.status == "accepted")

    def reverted_count(self) -> int:
        """Count of reverted repairs."""
        return sum(1 for r in self.records if r.status == "reverted")

    def summary(self) -> dict[str, Any]:
        """Summary metrics for stage export."""
        return {
            "total_repair_attempts": len(self.records),
            "accepted_repairs": self.accepted_count(),
            "reverted_repairs": self.reverted_count(),
            "total_tokens_used": self.total_tokens(),
            "repair_harm_rate": self.repair_harm_rate(),
        }
