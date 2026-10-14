"""
ExamForge v2: Isolated LLM / VLM Subsystem (Phase 1).

Enforces strict boundary control (Rule 8): all model access, token budgeting,
prompt caching, and cassette replay must route through this package.
"""

from __future__ import annotations

from examforge.llm.budget import BudgetExhaustedError, TokenBudget
from examforge.llm.cache import LLMCache
from examforge.llm.client import BaseLLMProvider, LLMClient
from examforge.llm.fake import FakeLLMClient
from examforge.llm.recording import (
    Cassette,
    CassetteMode,
    CassetteNotFoundError,
)
from examforge.llm.types import (
    ContentPart,
    LLMRequest,
    LLMResponse,
    Message,
    ModelSpec,
    Role,
    TokenUsage,
)

__all__ = [
    "BaseLLMProvider",
    "BudgetExhaustedError",
    "Cassette",
    "CassetteMode",
    "CassetteNotFoundError",
    "ContentPart",
    "FakeLLMClient",
    "LLMCache",
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "ModelSpec",
    "Role",
    "TokenBudget",
    "TokenUsage",
]
