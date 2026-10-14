"""
ExamForge v2: Content-Addressed LLM Prompt/Response Cache.

Provides deterministic caching keyed by SHA-256 digests of canonical request inputs.
Ensures zero redundant tokens are spent for identical prompts across runs.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from examforge.llm.types import LLMRequest, LLMResponse, TokenUsage


class LLMCache:
    """Persistent and in-memory content-addressed cache for LLM responses."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, LLMResponse] = {}
        self.hit_count: int = 0
        self.miss_count: int = 0

    def _path_for_key(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{key}.json"

    def get(self, request: LLMRequest) -> LLMResponse | None:
        """
        Retrieve cached response for a request, if available.

        Returns cloned response with cached=True and zero marginal token cost.
        """
        key = request.cache_key()

        # Check in-memory cache first
        if key in self._memory_cache:
            self.hit_count += 1
            cached_resp = self._memory_cache[key]
            return LLMResponse(
                content=cached_resp.content,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0, cost_usd=0.0),
                cached=True,
                model=cached_resp.model,
                finish_reason=cached_resp.finish_reason,
            )

        # Check disk cache
        path = self._path_for_key(key)
        if path is not None and path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
                resp = LLMResponse(
                    content=data["content"],
                    usage=TokenUsage(prompt_tokens=0, completion_tokens=0, cost_usd=0.0),
                    cached=True,
                    model=data.get("model", request.model),
                    finish_reason=data.get("finish_reason", "stop"),
                )
                self._memory_cache[key] = resp
                self.hit_count += 1
                return resp
            except Exception:
                pass

        self.miss_count += 1
        return None

    def set(self, request: LLMRequest, response: LLMResponse) -> None:
        """Store an LLM response in memory and on disk."""
        key = request.cache_key()
        self._memory_cache[key] = response

        path = self._path_for_key(key)
        if path is not None:
            payload = {
                "key": key,
                "model": response.model or request.model,
                "content": response.content,
                "usage": asdict(response.usage),
                "finish_reason": response.finish_reason,
            }
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            tmp_path.replace(path)

    def clear(self) -> None:
        """Clear in-memory and disk cache."""
        self._memory_cache.clear()
        if self.cache_dir is not None and self.cache_dir.exists():
            for p in self.cache_dir.glob("*.json"):
                p.unlink(missing_ok=True)
        self.hit_count = 0
        self.miss_count = 0
