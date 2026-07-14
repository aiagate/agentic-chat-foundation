"""Port for synchronizing the derived memory search projection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result


@dataclass
class MemoryIndexError(Exception):
    """Failure while synchronizing the memory projection."""

    message: str

    def __str__(self) -> str:
        return self.message


class IMemoryIndexProjection(ABC):
    """Internal projection boundary used after a memory write."""

    @abstractmethod
    async def refresh_for_user(
        self,
        *,
        user_id: str,
    ) -> Result[int, MemoryIndexError]:
        """Synchronize one user's current Markdown documents into SQL."""
        raise NotImplementedError
