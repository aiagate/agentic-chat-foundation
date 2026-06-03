"""Memory index maintenance port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.ports.memory_index import MemoryIndexError


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
