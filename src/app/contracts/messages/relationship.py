"""Shared relationship configuration and runtime DTOs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.aggregates.character_relationship import (
    RELATIONSHIP_STAGE_RANGES,
    RelationshipStageId,
)


class RelationshipSignalKind(StrEnum):
    """Semantic relationship change classifications."""

    STRONG_NEGATIVE = "strong_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    STRONG_POSITIVE = "strong_positive"


class RelationshipSignalStatus(StrEnum):
    """Lifecycle of a persisted relationship signal."""

    PROVISIONAL = "provisional"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class RelationshipBehaviorChoice(BaseModel):
    """One weighted prompt behavior available in a relationship stage."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    weight: int = Field(gt=0)
    instruction: str = Field(min_length=1)


class CharacterRelationshipStageDefinition(BaseModel):
    """Character-specific rendering rules for one shared stage."""

    model_config = ConfigDict(extra="forbid")

    id: RelationshipStageId
    description: str = Field(min_length=1)
    behaviors: list[RelationshipBehaviorChoice] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_behaviors(self) -> CharacterRelationshipStageDefinition:
        behavior_ids = [behavior.id for behavior in self.behaviors]
        if len(behavior_ids) != len(set(behavior_ids)):
            raise ValueError(f"duplicate behavior id in stage {self.id}")
        neutral = next(
            (behavior for behavior in self.behaviors if behavior.id == "neutral"),
            None,
        )
        if neutral is None or neutral.weight != 4:
            raise ValueError(f"stage {self.id} must define neutral with weight 4")
        specific = [behavior for behavior in self.behaviors if behavior.id != "neutral"]
        if len(specific) != 3 or any(behavior.weight != 2 for behavior in specific):
            raise ValueError(
                f"stage {self.id} must define three specific behaviors with weight 2"
            )
        return self


class CharacterRelationshipDefinition(BaseModel):
    """Strict character-owned relationship progression definition."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    signal_deltas: dict[RelationshipSignalKind, int]
    stages: list[CharacterRelationshipStageDefinition]

    @model_validator(mode="after")
    def validate_complete_definition(self) -> CharacterRelationshipDefinition:
        expected_signals = set(RelationshipSignalKind)
        if set(self.signal_deltas) != expected_signals:
            raise ValueError("signal_deltas must define every relationship signal")
        if self.signal_deltas[RelationshipSignalKind.NEUTRAL] != 0:
            raise ValueError("neutral relationship signal delta must be zero")
        expected_stages = {item.stage_id for item in RELATIONSHIP_STAGE_RANGES}
        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)) or set(stage_ids) != expected_stages:
            raise ValueError("stages must define every shared relationship stage once")
        return self

    def stage(
        self, stage_id: RelationshipStageId
    ) -> CharacterRelationshipStageDefinition:
        """Return one validated stage definition."""

        return next(stage for stage in self.stages if stage.id == stage_id)


class RelationshipSignalCandidate(BaseModel):
    """Validated LLM proposal for a relationship change."""

    model_config = ConfigDict(extra="forbid")

    kind: RelationshipSignalKind
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="")
    source_chat_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None


class RelationshipStateView(BaseModel):
    """Read-only relationship state used during response creation."""

    model_config = ConfigDict(extra="forbid")

    character_id: str
    user_id: str
    affection: int = Field(ge=0, le=100)
    stage_id: RelationshipStageId
    version: int = Field(ge=1)


class RelationshipBehaviorDirective(BaseModel):
    """Deterministically selected prompt-only behavior for one turn."""

    model_config = ConfigDict(extra="forbid")

    stage_id: RelationshipStageId
    behavior_id: str
    instruction: str


class PersistedRelationshipSignal(BaseModel):
    """Repository-facing relationship signal event."""

    model_config = ConfigDict(extra="forbid")

    id: str
    character_id: str
    user_id: str
    kind: RelationshipSignalKind
    status: RelationshipSignalStatus
    confidence: float = Field(ge=0.0, le=1.0)
    proposed_delta: int
    applied_delta: int = 0
    reason: str = ""
    source_chat_ids: list[str] = Field(min_length=1)
    observed_at: datetime
    created_at: datetime | None = None


RelationshipSignalMode = Literal["immediate", "daily"]


class RelationshipSignalEvaluationRequest(BaseModel):
    """Input to the external relationship signal evaluator."""

    model_config = ConfigDict(extra="forbid")

    mode: RelationshipSignalMode
    character_id: str
    user_id: str
    source_chat_ids: list[str] = Field(min_length=1)
    conversation_text: str = Field(min_length=1)
    observed_at: datetime
