"""Tests for TokenBudget governor (Phase 1)."""

from __future__ import annotations

import pytest

from examforge.llm.budget import BudgetExhaustedError, TokenBudget


def test_token_budget_normal_consumption():
    budget = TokenBudget(max_total_tokens=1000, max_tokens_per_question=200)
    budget.consume(prompt_tokens=100, completion_tokens=50, question_no=1)
    assert budget.total_spent == 150
    assert budget.per_question_spent[1] == 150
    assert budget.remaining_tokens() == 850


def test_token_budget_exceeds_question_cap():
    budget = TokenBudget(max_total_tokens=5000, max_tokens_per_question=200)
    budget.consume(prompt_tokens=100, completion_tokens=50, question_no=1)

    with pytest.raises(BudgetExhaustedError) as exc_info:
        budget.check_budget(tokens_to_spend=100, question_no=1)

    assert "Per-question token limit exceeded" in str(exc_info.value)
    assert exc_info.value.exit_code == "EXIT_NEEDS_REVIEW"
    assert exc_info.value.question_no == 1


def test_token_budget_exceeds_total_cap():
    budget = TokenBudget(max_total_tokens=500)
    budget.consume(prompt_tokens=300, completion_tokens=100)

    with pytest.raises(BudgetExhaustedError) as exc_info:
        budget.check_budget(tokens_to_spend=150)

    assert "Total run token limit exceeded" in str(exc_info.value)
    assert exc_info.value.exit_code == "EXIT_NEEDS_REVIEW"
