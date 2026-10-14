"""
ExamForge v2: Token and Cost Budget Governor.

Guarantees cost control by enforcing hard caps per run, per question,
and per stage. Exceeding any budget halts execution cleanly with
exit code EXIT_NEEDS_REVIEW and comprehensive evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BudgetExhaustedError(RuntimeError):
    """Raised when token or dollar budget is exhausted."""

    def __init__(
        self,
        reason: str,
        spent: int | float,
        limit: int | float,
        question_no: int | None = None,
        stage_name: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.spent = spent
        self.limit = limit
        self.question_no = question_no
        self.stage_name = stage_name
        self.exit_code = "EXIT_NEEDS_REVIEW"


@dataclass
class TokenBudget:
    """Governor enforcing token and dollar cost ceilings."""

    max_total_tokens: int = 100_000
    max_tokens_per_question: int = 4_000
    max_tokens_per_stage: int = 40_000
    max_cost_usd: float = 1.00

    total_spent: int = 0
    cost_spent: float = 0.0
    per_question_spent: dict[int, int] = field(default_factory=dict)
    per_stage_spent: dict[str, int] = field(default_factory=dict)

    def remaining_tokens(self) -> int:
        """Remaining tokens allowed for the current run."""
        return max(0, self.max_total_tokens - self.total_spent)

    def check_budget(
        self,
        tokens_to_spend: int,
        question_no: int | None = None,
        stage_name: str | None = None,
        cost_to_spend: float = 0.0,
    ) -> None:
        """
        Validate whether proposed token/cost expenditure is permitted.

        Raises BudgetExhaustedError if any threshold would be breached.
        """
        if self.total_spent + tokens_to_spend > self.max_total_tokens:
            new_tot = self.total_spent + tokens_to_spend
            raise BudgetExhaustedError(
                reason=f"Total run token limit exceeded: {new_tot} > {self.max_total_tokens}",
                spent=new_tot,
                limit=self.max_total_tokens,
                question_no=question_no,
                stage_name=stage_name,
            )

        if question_no is not None:
            q_current = self.per_question_spent.get(question_no, 0)
            if q_current + tokens_to_spend > self.max_tokens_per_question:
                new_q = q_current + tokens_to_spend
                raise BudgetExhaustedError(
                    reason=(
                        f"Per-question token limit exceeded for Q{question_no}: "
                        f"{new_q} > {self.max_tokens_per_question}"
                    ),
                    spent=new_q,
                    limit=self.max_tokens_per_question,
                    question_no=question_no,
                    stage_name=stage_name,
                )

        if stage_name is not None:
            s_current = self.per_stage_spent.get(stage_name, 0)
            if s_current + tokens_to_spend > self.max_tokens_per_stage:
                new_s = s_current + tokens_to_spend
                raise BudgetExhaustedError(
                    reason=(
                        f"Per-stage token limit exceeded for stage '{stage_name}': "
                        f"{new_s} > {self.max_tokens_per_stage}"
                    ),
                    spent=new_s,
                    limit=self.max_tokens_per_stage,
                    question_no=question_no,
                    stage_name=stage_name,
                )

        if self.cost_spent + cost_to_spend > self.max_cost_usd:
            new_cost = self.cost_spent + cost_to_spend
            raise BudgetExhaustedError(
                reason=(
                    f"Cost limit exceeded: "
                    f"${new_cost:.4f} > ${self.max_cost_usd:.4f}"
                ),
                spent=new_cost,
                limit=self.max_cost_usd,
                question_no=question_no,
                stage_name=stage_name,
            )

    def consume(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        question_no: int | None = None,
        stage_name: str | None = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Record actual tokens and cost consumed after an LLM call."""
        tokens = prompt_tokens + completion_tokens
        self.check_budget(
            tokens_to_spend=tokens,
            question_no=question_no,
            stage_name=stage_name,
            cost_to_spend=cost_usd,
        )

        self.total_spent += tokens
        self.cost_spent = round(self.cost_spent + cost_usd, 6)

        if question_no is not None:
            self.per_question_spent[question_no] = (
                self.per_question_spent.get(question_no, 0) + tokens
            )

        if stage_name is not None:
            self.per_stage_spent[stage_name] = (
                self.per_stage_spent.get(stage_name, 0) + tokens
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize budget state to dictionary."""
        return {
            "max_total_tokens": self.max_total_tokens,
            "max_tokens_per_question": self.max_tokens_per_question,
            "max_tokens_per_stage": self.max_tokens_per_stage,
            "max_cost_usd": self.max_cost_usd,
            "total_spent": self.total_spent,
            "cost_spent": self.cost_spent,
            "per_question_spent": dict(sorted(self.per_question_spent.items())),
            "per_stage_spent": dict(sorted(self.per_stage_spent.items())),
        }
