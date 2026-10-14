"""Tests for content-addressed LLM cache (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from examforge.llm.cache import LLMCache
from examforge.llm.types import LLMRequest, LLMResponse, Message, Role, TokenUsage


def test_cache_miss_and_set(tmp_path: Path):
    cache = LLMCache(cache_dir=tmp_path / "cache")
    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Translate formula to LaTeX")],
        model="gemini-1.5-flash",
    )

    assert cache.get(req) is None
    assert cache.miss_count == 1
    assert cache.hit_count == 0

    resp = LLMResponse(
        content=r"\alpha + \beta = \gamma",
        usage=TokenUsage(prompt_tokens=20, completion_tokens=10),
    )
    cache.set(req, resp)

    # Subsequent fetch should be a cache hit
    hit = cache.get(req)
    assert hit is not None
    assert hit.cached is True
    assert hit.content == r"\alpha + \beta = \gamma"
    assert cache.hit_count == 1


def test_cache_persistence_across_instances(tmp_path: Path):
    cache_dir = tmp_path / "persistent_cache"
    cache1 = LLMCache(cache_dir=cache_dir)
    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Persistent test prompt")],
        model="gpt-4o-mini",
    )
    resp = LLMResponse(
        content="Persistent response",
        usage=TokenUsage(prompt_tokens=15, completion_tokens=5),
    )
    cache1.set(req, resp)

    # New cache instance pointing to same directory
    cache2 = LLMCache(cache_dir=cache_dir)
    hit = cache2.get(req)
    assert hit is not None
    assert hit.content == "Persistent response"
    assert hit.cached is True
