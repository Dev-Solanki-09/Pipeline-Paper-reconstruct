"""Tests for FakeLLMClient offline mock (Phase 1)."""

from __future__ import annotations

from examforge.llm.fake import FakeLLMClient
from examforge.llm.types import LLMRequest, Message, Role


def test_fake_llm_default_response():
    fake = FakeLLMClient(default_content="Default simulated response")
    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Hello mock LLM")],
        model="fake-model",
    )
    resp = fake.complete(req)

    assert resp.content == "Default simulated response"
    assert resp.usage.total_tokens > 0
    assert len(fake.calls) == 1
    assert fake.calls[0] == req


def test_fake_llm_fifo_queue():
    fake = FakeLLMClient()
    fake.queue_response("Response 1")
    fake.queue_response("Response 2")

    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Query")],
        model="fake-model",
    )
    r1 = fake.complete(req)
    r2 = fake.complete(req)

    assert r1.content == "Response 1"
    assert r2.content == "Response 2"


def test_fake_llm_pattern_matching():
    fake = FakeLLMClient(default_content="Unmatched")
    fake.add_matcher("NEET 2024", '{"exam": "NEET", "year": 2024}')
    fake.add_matcher(
        lambda r: any("JEE" in str(m.content) for m in r.messages),
        '{"exam": "JEE"}',
    )

    resp_neet = fake.complete(
        LLMRequest(
            messages=[Message(role=Role.USER, content="Classify NEET 2024 paper")]
        )
    )
    resp_jee = fake.complete(
        LLMRequest(
            messages=[Message(role=Role.USER, content="Classify JEE paper")]
        )
    )
    resp_other = fake.complete(
        LLMRequest(
            messages=[Message(role=Role.USER, content="Classify UPSC paper")]
        )
    )

    assert resp_neet.content == '{"exam": "NEET", "year": 2024}'
    assert resp_jee.content == '{"exam": "JEE"}'
    assert resp_other.content == "Unmatched"
