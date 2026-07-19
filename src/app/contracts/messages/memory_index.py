"""Structured memory index DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.contracts.messages.memory_context import MemorySearchHit, MemorySource


@dataclass(frozen=True, slots=True)
class MemorySearchFilters:
    """Query filters for memory search."""

    user_id: str
    memory_type: str | None = None
    tags: tuple[str, ...] = ()
    date_from: datetime | str | None = None
    date_to: datetime | str | None = None
    status: str | None = None
    unresolved: bool | None = None
    timeline_type: str | None = None
    retention_state: str | None = None
    entity_type: str | None = None
    consolidation_state: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryIndexDocument:
    """Parsed memory document paired with its repository reference."""

    path: Path
    reference: str
    document: Any
    embedding: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemoryIndexRecord:
    """Persisted memory index projection."""

    source_path: str
    source_id: str
    user_id: str
    memory_type: str
    title: str | None
    content_hash: str
    indexed_text: str
    tags_json: str
    status: str | None
    timeline_type: str | None
    occurred_at: str | None
    updated_at: str
    importance: float
    confidence: float
    decay_score: float
    embedding: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """Search hit paired with the originating memory document."""

    hit: MemorySearchHit
    document: MemoryIndexDocument
    rank_score: float


@dataclass(frozen=True, slots=True)
class MemoryIndexSource:
    """Helper source payload for in-memory assembly."""

    source: MemorySource
