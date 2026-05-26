"""Structured memory context message DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["profile", "timeline", "entity"]
MemoryFrameSectionName = Literal["primary", "functional", "peripheral"]
MemoryScalar = str | int | float | bool
MemoryPropertyValue = MemoryScalar | list[MemoryScalar] | None


class MemoryProfile(BaseModel):
    """Stable profile memory surfaced to the application layer."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="User identifier.")
    display_name: str | None = Field(default=None, description="Display name.")
    summary: str = Field(default="", description="Profile summary.")
    traits: list[str] = Field(default_factory=list, description="Trait labels.")
    preferences: list[str] = Field(
        default_factory=list,
        description="Preference labels.",
    )


class MemoryTimelineEntry(BaseModel):
    """Timeline event surfaced by the memory service."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Entry identifier.")
    user_id: str = Field(description="User identifier.")
    kind: str = Field(description="Timeline kind.")
    content: str = Field(description="Entry content.")
    occurred_at: str = Field(description="Timestamp in ISO-8601 format.")
    source: str = Field(description="Entry source.")
    entity_ids: list[str] = Field(
        default_factory=list,
        description="Related entity identifiers.",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Opaque metadata values.",
    )


class MemoryEntity(BaseModel):
    """Normalized entity surfaced by the memory service."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Entity identifier.")
    user_id: str = Field(description="User identifier.")
    label: str = Field(description="Entity label.")
    entity_type: str = Field(description="Entity type.")
    status: str = Field(description="Entity status.")
    aliases: list[str] = Field(
        default_factory=list,
        description="Known aliases.",
    )
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Entity attributes.",
    )
    properties: dict[str, MemoryPropertyValue] = Field(
        default_factory=dict,
        description="Normalized entity properties.",
    )
    missing_attributes: list[str] = Field(
        default_factory=list,
        description="Known unresolved attributes for the entity.",
    )
    confidence: float = Field(description="Entity confidence.")


class MemorySource(BaseModel):
    """Opaque source attribution for a surfaced memory item."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable memory item identifier.")
    memory_type: MemoryType = Field(description="Memory layer for the source.")
    title: str | None = Field(
        default=None,
        description="Human-readable source title.",
    )
    user_id: str | None = Field(
        default=None,
        description="Owning user identifier, if user scoped.",
    )
    reference: str | None = Field(
        default=None,
        description="Opaque source reference for attribution.",
    )


class MemorySearchHit(BaseModel):
    """Search result metadata produced by the memory service."""

    model_config = ConfigDict(extra="forbid")

    source: MemorySource = Field(description="Matched memory source.")
    score: float = Field(description="Search relevance score.")
    matched_terms: list[str] = Field(
        default_factory=list,
        description="Normalized terms that matched this memory.",
    )
    excerpt: str = Field(
        default="",
        description="Short human-readable excerpt from the matched memory.",
    )


class MemoryFrameSection(BaseModel):
    """One ordered section of the assembled memory context frame."""

    model_config = ConfigDict(extra="forbid")

    name: MemoryFrameSectionName = Field(description="Context frame section name.")
    content: str = Field(description="Section text already assembled for prompting.")
    sources: list[MemorySource] = Field(
        default_factory=list,
        description="Sources represented in this section.",
    )


class MemoryContextFrame(BaseModel):
    """Assembled context frame returned by the memory service."""

    model_config = ConfigDict(extra="forbid")

    sections: list[MemoryFrameSection] = Field(
        default_factory=list,
        description="Ordered primary, functional, and peripheral sections.",
    )
    assembled_context: str = Field(
        default="",
        description="Prompt-ready memory context assembled by infrastructure.",
    )


class MemoryContextPack(BaseModel):
    """Materialized memory context used by the application layer."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="User identifier.")
    assembled_context: str | None = Field(
        default=None,
        description="Prompt-ready context assembled by the memory service.",
    )
    context_frame: MemoryContextFrame | None = Field(
        default=None,
        description="Structured context frame for diagnostics and future consumers.",
    )
    search_hits: list[MemorySearchHit] = Field(
        default_factory=list,
        description="Ranked memory search hits used to assemble the frame.",
    )
    profile: MemoryProfile | None = Field(
        default=None,
        description="Resolved profile memory.",
    )
    timelines: list[MemoryTimelineEntry] = Field(
        default_factory=list,
        description="Recent timeline entries.",
    )
    entities: list[MemoryEntity] = Field(
        default_factory=list,
        description="Relevant entities.",
    )
