"""Agent profile bundle DTOs and prompt rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts.messages.character_definition import (
    CharacterDefinition,
    RelationshipDefaults,
)
from app.contracts.messages.memory_context import MemoryProfile


@dataclass(frozen=True, slots=True)
class AgentProfileBundle:
    """Fully parsed built-in agent profile bundle."""

    profile: MemoryProfile
    character: CharacterDefinition
    persona_context: str
    communication_style: tuple[str, ...]
    known_constraints: tuple[str, ...]
    atmosphere: tuple[str, ...]
    behavior: tuple[str, ...]
    relationship_entity_id: str
    relationship_entity_label: str
    relationship_entity_type: str
    relationship_tag: str
    relationship: tuple[str, ...]
    fallback: tuple[str, ...]
    memory_reading_rules: tuple[str, ...]
    relationship_defaults: RelationshipDefaults = RelationshipDefaults()


def render_agent_persona_context(bundle: AgentProfileBundle) -> str:
    """Return the prompt-ready persona contract for the built-in agent."""

    return bundle.persona_context.strip()
