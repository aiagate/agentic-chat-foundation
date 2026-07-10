"""Memory index projection read boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.memory_index import MemoryIndexDocument


@dataclass
class MemoryIndexQueryError(Exception):
    """Failure while resolving memory documents from the projection."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryIndexQuery(ABC):
    """Resolve user-scoped memory documents through the main DB projection."""

    @abstractmethod
    async def list_documents(
        self,
        *,
        user_id: str,
        character_id: str,
        relationship_entity_id: str,
    ) -> Result[list[MemoryIndexDocument], MemoryIndexQueryError]:
        """Return projected documents visible to one user and character."""
        raise NotImplementedError
