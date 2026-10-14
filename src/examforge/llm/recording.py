"""
ExamForge v2: LLM Cassette Recording and Playback.

Enables full determinism and offline testing (Rule 7) by recording model
interactions to versioned JSON cassettes during manual recording runs,
and replaying them in automated test suites without any network access.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import Any

from examforge.llm.types import LLMRequest, LLMResponse, TokenUsage


class CassetteMode(StrEnum):
    """Execution mode for cassette."""

    RECORD = "record"
    PLAYBACK = "playback"
    PASSTHROUGH = "passthrough"


class CassetteNotFoundError(RuntimeError):
    """Raised when an unrecorded request is encountered during playback."""


class Cassette:
    """Stores and replays LLM interactions from a structured JSON cassette."""

    def __init__(self, path: Path, mode: CassetteMode = CassetteMode.PLAYBACK) -> None:
        self.path = path
        self.mode = mode
        self.interactions: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load recorded interactions if the cassette file exists."""
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        key = item.get("key")
                        if key:
                            self.interactions[key] = item
                elif isinstance(data, dict):
                    self.interactions = data
            except Exception:
                self.interactions = {}

    def record(self, request: LLMRequest, response: LLMResponse) -> None:
        """Record an interaction under its deterministic request key."""
        key = request.cache_key()
        self.interactions[key] = {
            "key": key,
            "model": response.model or request.model,
            "content": response.content,
            "usage": asdict(response.usage),
            "finish_reason": response.finish_reason,
        }

    def playback(self, request: LLMRequest) -> LLMResponse:
        """Retrieve and reconstruct recorded response for a request."""
        key = request.cache_key()
        if key not in self.interactions:
            raise CassetteNotFoundError(
                f"No recorded cassette response for request key: {key} "
                f"(model: {request.model}). Re-record cassettes using make record-cassettes."
            )

        data = self.interactions[key]
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            cost_usd=usage_data.get("cost_usd", 0.0),
        )

        return LLMResponse(
            content=data["content"],
            usage=usage,
            cached=True,
            model=data.get("model", request.model),
            finish_reason=data.get("finish_reason", "stop"),
        )

    def save(self) -> None:
        """Persist interactions sorted by key for deterministic git diffs."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_interactions = [
            self.interactions[k] for k in sorted(self.interactions.keys())
        ]
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sorted_interactions, f, indent=2, sort_keys=True)
        tmp_path.replace(self.path)

    def __enter__(self) -> Cassette:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.mode == CassetteMode.RECORD:
            self.save()
