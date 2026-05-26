"""Memory index port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flow_res import Result


@dataclass(frozen=True)
class MemoryIndexError(Exception):
    """Represents a memory index failure."""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class MemoryIndexRecord:
    """Persisted metadata projection for an indexed memory source."""

    source_path: str
    source_id: str
    content_hash: str
    indexed_text: str
    tags_json: str


class IMemoryIndex(ABC):
    """Interface for deterministic memory indexing and search."""

    @abstractmethod
    def index_document_from_stored(
        self,
        stored: Any,
        *,
        root: Path,
    ) -> Any:
        """Build an indexable document from a stored memory document."""
        ...

    @abstractmethod
    def search_memory_index(
        self,
        query: str,
        documents: Sequence[Any],
        filters: Any,
        *,
        limit: int = 20,
    ) -> list[Any]:
        """Search documents and return ranked hits."""
        ...

    @abstractmethod
    def rebuild_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Rebuild the persistent memory index from Markdown sources."""

    @abstractmethod
    def repair_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Repair stale or missing persistent memory index rows."""
