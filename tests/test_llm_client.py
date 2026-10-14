"""Tests for unified LLMClient facade (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from examforge.llm.budget import TokenBudget
from examforge.llm.cache import LLMCache
from examforge.llm.client import LLMClient
from examforge.llm.fake import FakeLLMClient
from examforge.llm.types import LLMRequest, Message, Role
from examforge.telemetry import TelemetryLedger


def test_llm_client_pipeline_integration(tmp_path: Path):
    fake = FakeLLMClient(default_content='{"verified": true}')
    cache = LLMCache(cache_dir=tmp_path / "cache")
    budget = TokenBudget(max_total_tokens=1000)
    ledger = TelemetryLedger(run_id="test_run_pipeline")

    client = LLMClient(
        provider=fake,
        cache=cache,
        budget=budget,
        telemetry=ledger,
    )

    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Verify question 5")],
        question_no=5,
        stage_name="s8_verify",
    )

    # 1. First call: cache miss -> invokes provider -> consumes budget & telemetry -> caches
    resp1 = client.complete(req)
    assert resp1.content == '{"verified": true}'
    assert resp1.cached is False
    assert len(fake.calls) == 1
    assert budget.total_spent == 60  # 40 prompt + 20 comp
    assert 5 in ledger.questions_touched_by_llm

    # 2. Second identical call: cache hit -> 0 provider calls -> 0 marginal budget
    resp2 = client.complete(req)
    assert resp2.content == '{"verified": true}'
    assert resp2.cached is True
    assert len(fake.calls) == 1  # provider NOT called again
    assert budget.total_spent == 60  # no additional tokens spent
