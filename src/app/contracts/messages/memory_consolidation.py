"""Messages exchanged by long-term-memory consolidation boundaries."""

from dataclasses import dataclass

from app.contracts.messages.memory_semantic_extraction import (
    MemoryEntityPatch,
    MemoryProfilePatch,
    MemoryTimelineSectionPatch,
)
from app.contracts.messages.relationship import RelationshipSignalCandidate


@dataclass(frozen=True, slots=True)
class MemoryChangeSet:
    """Fully validated, side-effect-free changes for one memory batch."""

    sections: tuple[MemoryTimelineSectionPatch, ...]
    entities: tuple[MemoryEntityPatch, ...]
    profile: MemoryProfilePatch | None
    evaluated_chat_ids: tuple[str, ...]
    deferred_chat_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MemoryConsolidationResult:
    """Applied changes and source dispositions for one user/day batch."""

    evaluated_chat_ids: tuple[str, ...]
    deferred_chat_ids: tuple[str, ...]
    profile_updated: bool = False
    episode_upserted_count: int = 0
    entity_upserted_count: int = 0
    relationship_signals: tuple[RelationshipSignalCandidate, ...] = ()
