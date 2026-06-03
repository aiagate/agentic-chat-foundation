"""Memory write service port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result


@dataclass(frozen=True)
class MemoryWriteServiceError(Exception):
    """Represents a memory write adapter failure."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryWriteService(ABC):
    """Persist write-side memory artifacts."""

    @abstractmethod
    async def add_log(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, str],
    ) -> Result[None, MemoryWriteServiceError]:
        """Store a conversation log entry for future memory consolidation."""
        raise NotImplementedError
