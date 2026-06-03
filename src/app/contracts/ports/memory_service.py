"""Memory service port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.memory_context import MemoryContextPack


@dataclass
class MemoryServiceError(Exception):
    """Represents a memory service failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryService(ABC):
    """Interface for memory retrieval."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a user-scoped context pack with assembled prompt context."""
