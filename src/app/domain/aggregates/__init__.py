"""Domain aggregates."""

from app.domain.aggregates.character_relationship import (
    CharacterRelationship,
    RelationshipStageId,
    RelationshipStageRange,
    resolve_relationship_stage,
)
from app.domain.aggregates.user import User, UserChannelIdentity

__all__ = [
    "CharacterRelationship",
    "RelationshipStageId",
    "RelationshipStageRange",
    "User",
    "UserChannelIdentity",
    "resolve_relationship_stage",
]
