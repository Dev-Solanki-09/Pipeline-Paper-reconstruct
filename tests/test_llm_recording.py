"""Tests for LLM cassette recording and playback (Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from examforge.llm.recording import (
    Cassette,
    CassetteMode,
    CassetteNotFoundError,
)
from examforge.llm.types import LLMRequest, LLMResponse, Message, Role, TokenUsage


def test_cassette_record_and_playback(tmp_path: Path):
    cassette_path = tmp_path / "test_cassette.json"
    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Translate Question 10")],
        model="mock-vlm",
    )
    resp = LLMResponse(
        content='{"translated": "प्रश्न 10"}',
        usage=TokenUsage(prompt_tokens=30, completion_tokens=15),
    )

    # 1. Record mode
    cassette = Cassette(path=cassette_path, mode=CassetteMode.RECORD)
    cassette.record(req, resp)
    cassette.save()

    assert cassette_path.exists()

    # 2. Playback mode (simulating offline test execution)
    playback_cassette = Cassette(path=cassette_path, mode=CassetteMode.PLAYBACK)
    replayed = playback_cassette.playback(req)

    assert replayed.content == '{"translated": "प्रश्न 10"}'
    assert replayed.usage.prompt_tokens == 30
    assert replayed.usage.completion_tokens == 15


def test_cassette_missing_interaction_raises_error(tmp_path: Path):
    cassette_path = tmp_path / "empty_cassette.json"
    cassette_path.write_text("[]", encoding="utf-8")

    playback_cassette = Cassette(path=cassette_path, mode=CassetteMode.PLAYBACK)
    req = LLMRequest(
        messages=[Message(role=Role.USER, content="Unrecorded query")],
        model="mock-vlm",
    )

    with pytest.raises(CassetteNotFoundError) as exc_info:
        playback_cassette.playback(req)

    assert "No recorded cassette response for request key" in str(exc_info.value)
