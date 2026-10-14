"""Tests for ExamForge v2 LLM types (Phase 1)."""

from __future__ import annotations

import pytest

from examforge.llm.types import (
    LLMRequest,
    LLMResponse,
    Message,
    ModelSpec,
    Role,
    TokenUsage,
)


def test_token_usage_cost_calculation():
    spec = ModelSpec(
        model_name="claude-3-5-sonnet",
        provider="anthropic",
        cost_per_1k_prompt=0.003,
        cost_per_1k_completion=0.015,
    )
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=200)
    assert usage.total_tokens == 1200
    cost = usage.calculate_cost(spec)
    # 1000/1000 * 0.003 + 200/1000 * 0.015 = 0.003 + 0.003 = 0.006
    assert cost == pytest.approx(0.006)
    assert usage.cost_usd == pytest.approx(0.006)


def test_llm_request_deterministic_cache_key():
    req1 = LLMRequest(
        messages=[
            Message(role=Role.SYSTEM, content="You are an exam validator."),
            Message(role=Role.USER, content="Validate formula: E = mc^2"),
        ],
        model="gemini-1.5-flash",
        temperature=0.0,
    )
    req2 = LLMRequest(
        messages=[
            Message(role=Role.SYSTEM, content="You are an exam validator."),
            Message(role=Role.USER, content="Validate formula: E = mc^2"),
        ],
        model="gemini-1.5-flash",
        temperature=0.0,
    )
    req3 = LLMRequest(
        messages=[
            Message(role=Role.SYSTEM, content="You are an exam validator."),
            Message(role=Role.USER, content="Validate formula: F = ma"),
        ],
        model="gemini-1.5-flash",
        temperature=0.0,
    )

    assert req1.cache_key() == req2.cache_key()
    assert req1.cache_key() != req3.cache_key()
    assert len(req1.cache_key()) == 64  # SHA-256 hex digest


def test_llm_response_json_parsing():
    resp = LLMResponse(
        content='{"status": "valid", "formula": "E=mc^2"}',
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10),
    )
    parsed = resp.parse_json()
    assert parsed == {"status": "valid", "formula": "E=mc^2"}
