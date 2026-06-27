"""Stable metadata for one built-in agent character."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelationshipDefaults:
    """Default relationship values for one character."""

    trust_score: float = 0.0
    warmth_score: float = 0.0
    stage: int = 0


@dataclass(frozen=True, slots=True)
class CharacterDefinition:
    """Stable metadata for one built-in agent character."""

    character_id: str
    relationship_entity_id: str
    relationship_entity_label: str
    relationship_entity_type: str = "relationship"
    relationship_tag: str = "agent-growth"
    profile_user_id: str = "ai"
    relationship_defaults: RelationshipDefaults = RelationshipDefaults()
