"""
ExamForge v2: Unified LLM Client Facade.

Enforces Rule 8: All model access passes through this facade, which wraps
the underlying provider with content-addressed caching, token budget enforcement,
cassette recording/playback, and telemetry ledger tracking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from examforge.llm.recording import CassetteMode
from examforge.llm.types import LLMRequest, LLMResponse

if TYPE_CHECKING:
    from examforge.llm.budget import TokenBudget
    from examforge.llm.cache import LLMCache
    from examforge.llm.recording import Cassette
    from examforge.telemetry import TelemetryLedger


class BaseLLMProvider(ABC):
    """Abstract interface for LLM/VLM model providers."""

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute completion for a request."""


class LLMClient:
    """
    Main gateway for LLM calls across the ExamForge pipeline.

    Orchestrates caching, budget governors, cassette replay, and telemetry.
    """

    def __init__(
        self,
        provider: Any,
        cache: LLMCache | None = None,
        budget: TokenBudget | None = None,
        cassette: Cassette | None = None,
        telemetry: TelemetryLedger | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.budget = budget
        self.cassette = cassette
        self.telemetry = telemetry

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Execute an LLM request with caching, budget verification, and telemetry.
        """
        # 1. Cassette playback mode (offline determinism)
        if self.cassette is not None and self.cassette.mode == CassetteMode.PLAYBACK:
            resp = self.cassette.playback(request)
            if self.telemetry is not None:
                self.telemetry.record_llm_usage(
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                    cost_usd=resp.usage.cost_usd,
                    question_no=request.question_no,
                    stage_name=request.stage_name,
                )
            return resp

        # 2. Check content-addressed cache
        if self.cache is not None:
            cached_resp = self.cache.get(request)
            if cached_resp is not None:
                return cached_resp

        # 3. Check budget before invoking provider
        if self.budget is not None:
            # Estimate prompt tokens based on message lengths
            estimated_prompt_tokens = sum(
                len(str(m.content)) for m in request.messages
            ) // 4 + 10
            self.budget.check_budget(
                tokens_to_spend=estimated_prompt_tokens,
                question_no=request.question_no,
                stage_name=request.stage_name,
            )

        # 4. Invoke provider
        response = self.provider.complete(request)

        # 5. Consume budget & update telemetry
        if self.budget is not None:
            self.budget.consume(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                question_no=request.question_no,
                stage_name=request.stage_name,
                cost_usd=response.usage.cost_usd,
            )

        if self.telemetry is not None:
            self.telemetry.record_llm_usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                cost_usd=response.usage.cost_usd,
                question_no=request.question_no,
                stage_name=request.stage_name,
            )

        # 6. Cassette record mode
        if self.cassette is not None and self.cassette.mode == CassetteMode.RECORD:
            self.cassette.record(request, response)

        # 7. Store in cache
        if self.cache is not None:
            self.cache.set(request, response)

        return response
