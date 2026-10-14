"""Embeddings interface for Question Bank (Phase 12.6). Optional, off by default."""

from __future__ import annotations

from typing import Protocol


class EmbeddingModel(Protocol):
    """Protocol for optional vector embedding models."""

    def embed_text(self, text: str) -> list[float]:
        """Compute float embedding vector for text."""
        ...


class DisabledEmbeddingModel:
    """Default no-op embedding model when bank.embeddings is false."""

    def embed_text(self, text: str) -> list[float]:
        """No-op returning empty vector."""
        return []
