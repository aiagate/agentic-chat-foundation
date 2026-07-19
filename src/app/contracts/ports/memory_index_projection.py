"""Port for synchronizing the derived memory search projection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

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
    async def apply_changes(
        self,
        *,
        user_id: str,
        upsert_paths: list[Path],
        delete_paths: list[Path],
    ) -> Result[int, MemoryIndexError]:
        """Apply changed Markdown paths to one user's SQL projection."""
        raise NotImplementedError
