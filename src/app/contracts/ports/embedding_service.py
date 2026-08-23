"""Embedding service port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result


@dataclass
class EmbeddingServiceError(Exception):
    """Represents an embedding service failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IEmbeddingService(ABC):
    """Interface for text embedding generation."""

    @abstractmethod
    async def embed_texts(
        self,
        texts: list[str],
    ) -> Result[list[list[float]], EmbeddingServiceError]:
        """Return embedding vectors for the supplied text list."""
