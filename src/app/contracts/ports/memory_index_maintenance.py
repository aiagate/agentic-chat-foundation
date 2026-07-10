"""Memory index maintenance port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result


@dataclass
class MemoryIndexError(Exception):
    """Failure while rebuilding or repairing the memory index projection."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryIndexMaintenance(ABC):
    """Interface for rebuilding and repairing memory index projections."""

    @abstractmethod
    async def rebuild_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Rebuild the persistent memory index from Markdown sources."""

    @abstractmethod
    async def repair_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Repair stale or missing persistent memory index rows."""
