"""Structured memory semantic extraction DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.relationship import RelationshipSignalCandidate


class LongTermMemoryChatLog(BaseModel):
    """Normalized raw chat log input for long-term memory extraction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable source chat identifier.")
    user_id: str = Field(description="Owning user identifier.")
    character_id: str = Field(description="Character boundary of the source chat.")
    role: str = Field(description="Message role.")
    chat_type: ChatType = Field(description="Chat channel type.")
    content: str = Field(description="Normalized message text.")
    occurred_at: datetime = Field(description="Observed timestamp.")


class MemoryEvidence(BaseModel):
    """Source evidence used for a memory patch."""

    model_config = ConfigDict(extra="forbid")

    notes: list[str] = Field(
        default_factory=list,
        description="Short justification notes.",
    )


class MemorySectionSummary(BaseModel):
    """Structured episodic summary used for Timeline content."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="What was discussed.")
    self_feeling: str = Field(description="How the user seemed to feel.")
    other_feeling: str = Field(description="How the other side seemed to feel.")
    outcome: str = Field(description="What remained as a result or decision.")


class MemoryTimelineSectionPatch(BaseModel):
    """Proposed section-scoped Timeline memory update."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable section memory id.")
    user_id: str = Field(description="Owning user identifier.")
    day: str = Field(description="Timeline day in YYYY-MM-DD format.")
    section_slug: str = Field(description="Stable section slug.")
    title: str = Field(description="Human-readable section title.")
    source_chat_ids: list[str] = Field(
        min_length=1,
        description="Source chat identifiers belonging to this section.",
    )
    summary: MemorySectionSummary = Field(description="Structured episode summary.")
    entity_ids: list[str] = Field(
        default_factory=list,
        description="Related entity identifiers.",
    )
    confidence: float = Field(description="Extraction confidence.")


class MemoryEntityPatch(BaseModel):
    """Proposed Entity memory update."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Entity identifier.")
    user_id: str = Field(description="Owning user identifier.")
    label: str = Field(description="Entity label.")
    entity_type: str = Field(description="Entity type.")
    status: str = Field(description="Entity status.")
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, str | int | float | bool | list[str] | None] = Field(
        default_factory=dict
    )
    missing_attributes: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Extraction confidence.")
    source_chat_ids: list[str] = Field(
        default_factory=list,
        description="Raw chat evidence for this entity change.",
    )
    observed_at: datetime | None = Field(default=None)
    update_mode: Literal["merge", "replace", "transition", "defer"] = "merge"


class MemoryProfilePatch(BaseModel):
    """Proposed profile update."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="Owning user identifier.")
    summary: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    traits: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Extraction confidence.")
    source_chat_ids: list[str] = Field(
        default_factory=list,
        description="Raw chat evidence for this profile change.",
    )
    observed_at: datetime | None = Field(default=None)
    update_mode: Literal["merge", "replace", "defer"] = "merge"


class MemorySourceEvaluation(BaseModel):
    """Disposition assigned to one raw chat input."""

    model_config = ConfigDict(extra="forbid")

    chat_id: str
    disposition: Literal["used", "not_memorable", "deferred"]
    reason: str = ""


class MemorySemanticExtractionRequest(BaseModel):
    """Input payload for memory semantic extraction."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    day: str
    raw_logs: list[LongTermMemoryChatLog] = Field(default_factory=list)
    existing_profile_summary: str | None = None
    existing_entity_labels: list[str] = Field(default_factory=list)
    existing_timeline_summaries: list[str] = Field(default_factory=list)


class MemorySemanticExtractionResult(BaseModel):
    """Validated extraction output returned by the memory LLM."""

    model_config = ConfigDict(extra="forbid")

    sections: list[MemoryTimelineSectionPatch] = Field(default_factory=list)
    entity_patches: list[MemoryEntityPatch] = Field(default_factory=list)
    profile_patch: MemoryProfilePatch | None = None
    evidence: MemoryEvidence = Field(default_factory=MemoryEvidence)
    source_evaluations: list[MemorySourceEvaluation] = Field(default_factory=list)
    relationship_signals: list[RelationshipSignalCandidate] = Field(
        default_factory=list,
        description="Confirmed relationship signals supported by raw chat evidence.",
    )
