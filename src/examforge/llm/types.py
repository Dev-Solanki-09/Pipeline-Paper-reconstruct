"""
ExamForge v2: LLM Types and Data Models.

Defines typed request/response contracts, model pricing specifications,
token usage accounting, and deterministic hashing for caching.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Message sender role."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ContentPart:
    """Multimodal content part (text or image)."""

    type: str  # "text" or "image_base64" or "image_url"
    text: str | None = None
    image_data: str | None = None
    mime_type: str | None = None


@dataclass
class Message:
    """Chat message exchanged with an LLM."""

    role: Role | str
    content: str | list[ContentPart]

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        role_str = self.role.value if isinstance(self.role, Role) else str(self.role)
        if isinstance(self.content, str):
            return {"role": role_str, "content": self.content}
        return {
            "role": role_str,
            "content": [asdict(part) for part in self.content],
        }


@dataclass
class ModelSpec:
    """Cost and capability specification for a supported model."""

    model_name: str
    provider: str  # "openai", "anthropic", "gemini", "local", "fake"
    cost_per_1k_prompt: float = 0.0
    cost_per_1k_completion: float = 0.0
    supports_vision: bool = True


@dataclass
class TokenUsage:
    """Token counts and estimated dollar cost for an inference call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    def calculate_cost(self, spec: ModelSpec) -> float:
        """Calculate and record USD cost using the model specification."""
        prompt_cost = (self.prompt_tokens / 1000.0) * spec.cost_per_1k_prompt
        completion_cost = (self.completion_tokens / 1000.0) * spec.cost_per_1k_completion
        self.cost_usd = round(prompt_cost + completion_cost, 6)
        return self.cost_usd


@dataclass
class LLMRequest:
    """Structured request sent to an LLM provider."""

    messages: list[Message]
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 2048
    response_format: str = "text"  # "text" or "json"
    question_no: int | None = None
    stage_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def cache_key(self) -> str:
        """
        Compute a deterministic SHA-256 hash of the request parameters.

        Sorted iteration and normalized serialization guarantee reproducibility.
        """
        normalized_data = {
            "model": self.model,
            "temperature": round(self.temperature, 4),
            "max_tokens": self.max_tokens,
            "response_format": self.response_format,
            "messages": [msg.to_dict() for msg in self.messages],
        }
        encoded = json.dumps(normalized_data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass
class LLMResponse:
    """Standardized response received from an LLM call."""

    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    cached: bool = False
    model: str = ""
    finish_reason: str = "stop"

    def parse_json(self) -> dict[str, Any]:
        """
        Parse response content as JSON.

        Handles markdown code fences if present.
        """
        text = self.content.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
