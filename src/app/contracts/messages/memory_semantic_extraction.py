"""Structured memory semantic extraction DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.messages.chat_type import ChatType


class MemorySleepChatLog(BaseModel):
    """Normalized raw chat log input for memory extraction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable source chat identifier.")
    user_id: str = Field(description="Owning user identifier.")
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
    """Structured daily summary used for Timeline content."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="What was discussed.")
    self_feeling: str = Field(description="How the user seemed to feel.")
    other_feeling: str = Field(description="How the other side seemed to feel.")
    outcome: str = Field(description="What remained as a result or decision.")


class MemoryTimelinePatch(BaseModel):
    """Proposed Timeline memory update."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable timeline memory id.")
    user_id: str = Field(description="Owning user identifier.")
    day: str = Field(description="Timeline day in YYYY-MM-DD format.")
    summary: MemorySectionSummary = Field(description="Structured daily summary.")
    entity_ids: list[str] = Field(
        default_factory=list,
        description="Related entity identifiers.",
    )
    confidence: float = Field(description="Extraction confidence.")


class MemoryTimelineSectionPatch(BaseModel):
    """Proposed section-scoped Timeline memory update."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable section memory id.")
    user_id: str = Field(description="Owning user identifier.")
    day: str = Field(description="Timeline day in YYYY-MM-DD format.")
    section_slug: str = Field(description="Stable section slug.")
    title: str = Field(description="Human-readable section title.")
    summary: MemorySectionSummary = Field(description="Structured daily summary.")
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
    attributes: dict[str, str] = Field(default_factory=dict)
    properties: dict[str, str | int | float | bool | list[str] | None] = Field(
        default_factory=dict
    )
    missing_attributes: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Extraction confidence.")


class MemoryProfilePatch(BaseModel):
    """Proposed profile update."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(description="Owning user identifier.")
    summary: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    traits: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    confidence: float = Field(description="Extraction confidence.")


class MemorySemanticExtractionRequest(BaseModel):
    """Input payload for memory semantic extraction."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    day: str
    raw_logs: list[MemorySleepChatLog] = Field(default_factory=list)
    existing_profile_summary: str | None = None
    existing_entity_labels: list[str] = Field(default_factory=list)
    existing_timeline_summaries: list[str] = Field(default_factory=list)


class MemorySemanticExtractionResult(BaseModel):
    """Validated extraction output returned by the memory LLM."""

    model_config = ConfigDict(extra="forbid")

    timeline_patch: MemoryTimelinePatch | None = None
    sections: list[MemoryTimelineSectionPatch] = Field(default_factory=list)
    entity_patches: list[MemoryEntityPatch] = Field(default_factory=list)
    profile_patch: MemoryProfilePatch | None = None
    evidence: MemoryEvidence = Field(default_factory=MemoryEvidence)
