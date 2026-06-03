"""Memory index port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar


@dataclass
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


TStored = TypeVar("TStored")
TDocument = TypeVar("TDocument")
THit = TypeVar("THit")
TFilters = TypeVar("TFilters")


class IMemoryIndex[TStored, TDocument, THit, TFilters](ABC):
    """Interface for deterministic memory indexing and search."""

    @abstractmethod
    def index_document_from_stored(
        self,
        stored: TStored,
        *,
        root: Path,
    ) -> TDocument:
        """Build an indexable document from a stored memory document."""
        ...

    @abstractmethod
    def search_memory_index(
        self,
        query: str,
        documents: Sequence[TDocument],
        filters: TFilters,
        *,
        root: Path | None = None,
        index_db_path: Path | None = None,
        embedding_service: object | None = None,
        query_embedding: list[float] | None = None,
        limit: int = 20,
    ) -> list[THit]:
        """Search documents and return ranked hits."""
        ...
