"""Character-to-user relationship domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

MIN_AFFECTION = 0
MAX_AFFECTION = 100
MAX_DAILY_AFFECTION_INCREASE = 5
MAX_DAILY_AFFECTION_DECREASE = 10
MIN_SIGNAL_CONFIDENCE = 0.8


class RelationshipStageId(StrEnum):
    """Stable stage identifiers shared by every character."""

    DISTANT = "distant"
    RECOGNIZED = "recognized"
    INTERESTED = "interested"
    AFFECTIONATE = "affectionate"
    TRUSTING = "trusting"
    INTIMATE = "intimate"
    ATTACHED = "attached"
    DEVOTED = "devoted"


@dataclass(frozen=True, slots=True)
class RelationshipStageRange:
    """Inclusive affection range for a shared relationship stage."""

    stage_id: RelationshipStageId
    minimum: int
    maximum: int


RELATIONSHIP_STAGE_RANGES: tuple[RelationshipStageRange, ...] = (
    RelationshipStageRange(RelationshipStageId.DISTANT, 0, 10),
    RelationshipStageRange(RelationshipStageId.RECOGNIZED, 11, 25),
    RelationshipStageRange(RelationshipStageId.INTERESTED, 26, 40),
    RelationshipStageRange(RelationshipStageId.AFFECTIONATE, 41, 55),
    RelationshipStageRange(RelationshipStageId.TRUSTING, 56, 70),
    RelationshipStageRange(RelationshipStageId.INTIMATE, 71, 85),
    RelationshipStageRange(RelationshipStageId.ATTACHED, 86, 95),
    RelationshipStageRange(RelationshipStageId.DEVOTED, 96, 100),
)


@dataclass(frozen=True, slots=True)
class CharacterRelationship:
    """Persisted affection state between one character and one user."""

    character_id: str
    user_id: str
    affection: int = 0
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.character_id.strip():
            raise ValueError("character_id must not be empty")
        if not self.user_id.strip():
            raise ValueError("user_id must not be empty")
        if not MIN_AFFECTION <= self.affection <= MAX_AFFECTION:
            raise ValueError("affection must be between 0 and 100")
        if self.version < 1:
            raise ValueError("version must be positive")


def clamp_affection(value: int) -> int:
    """Clamp an affection value to its domain range."""

    return min(max(value, MIN_AFFECTION), MAX_AFFECTION)


def resolve_relationship_stage(affection: int) -> RelationshipStageId:
    """Resolve the shared relationship stage for one affection value."""

    bounded = clamp_affection(affection)
    for stage_range in RELATIONSHIP_STAGE_RANGES:
        if stage_range.minimum <= bounded <= stage_range.maximum:
            return stage_range.stage_id
    raise AssertionError("relationship stage ranges must cover 0 through 100")
