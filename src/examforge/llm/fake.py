"""
ExamForge v2: Deterministic Offline Fake LLM Client.

Provides programmable responses, FIFO queues, and pattern-based matchers
for offline unit and regression testing with zero socket calls.
"""

from __future__ import annotations

from collections.abc import Callable

from examforge.llm.types import LLMRequest, LLMResponse, TokenUsage


class FakeLLMClient:
    """Mock LLM client executing deterministically in memory without network."""

    def __init__(
        self,
        default_content: str = "{}",
        simulated_prompt_tokens: int = 40,
        simulated_completion_tokens: int = 20,
    ) -> None:
        self.default_content = default_content
        self.simulated_prompt_tokens = simulated_prompt_tokens
        self.simulated_completion_tokens = simulated_completion_tokens
        self.calls: list[LLMRequest] = []
        self._queue: list[LLMResponse | str] = []
        self._matchers: list[tuple[Callable[[LLMRequest], bool] | str, LLMResponse | str]] = []

    def queue_response(self, response: LLMResponse | str) -> None:
        """Enqueue a response to be returned by next complete() call in FIFO order."""
        self._queue.append(response)

    def add_matcher(
        self,
        predicate: Callable[[LLMRequest], bool] | str,
        response: LLMResponse | str,
    ) -> None:
        """
        Add a rule mapping requests to responses.

        If predicate is a string, checks if it appears in any message text.
        If predicate is a callable, invokes predicate(request).
        """
        self._matchers.append((predicate, response))

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete a simulated request deterministically."""
        self.calls.append(request)

        # 1. Check queued responses
        if self._queue:
            item = self._queue.pop(0)
            return self._to_response(item, request)

        # 2. Check pattern matchers
        for predicate, resp_item in self._matchers:
            matched = False
            if isinstance(predicate, str):
                for msg in request.messages:
                    if isinstance(msg.content, str) and predicate in msg.content:
                        matched = True
                        break
            elif callable(predicate):
                try:
                    matched = bool(predicate(request))
                except Exception:
                    matched = False

            if matched:
                return self._to_response(resp_item, request)

        # 3. Fallback to default response
        return self._to_response(self.default_content, request)

    def _to_response(self, item: LLMResponse | str, request: LLMRequest) -> LLMResponse:
        if isinstance(item, LLMResponse):
            return item

        prompt_toks = self.simulated_prompt_tokens
        comp_toks = self.simulated_completion_tokens
        return LLMResponse(
            content=str(item),
            usage=TokenUsage(
                prompt_tokens=prompt_toks,
                completion_tokens=comp_toks,
                total_tokens=prompt_toks + comp_toks,
            ),
            cached=False,
            model=request.model or "fake-model",
            finish_reason="stop",
        )

    def reset(self) -> None:
        """Clear call history, queue, and matchers."""
        self.calls.clear()
        self._queue.clear()
        self._matchers.clear()
