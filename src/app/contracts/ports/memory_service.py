"""Memory service port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.memory_context import MemoryContextPack, MemoryReadResult


@dataclass
class MemoryServiceError(Exception):
    """Represents a memory service failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryService(ABC):
    """Interface for memory retrieval."""

    @abstractmethod
    async def build_context(
        self,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a user-scoped compact manifest for prompt injection."""

    @abstractmethod
    async def read_memory(
        self,
        memory_id: str,
        user_id: str,
    ) -> Result[MemoryReadResult, MemoryServiceError]:
        """Resolve one full memory document addressed by memory_id."""
