"""Agent profile bundle DTOs and prompt rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.relationship import CharacterRelationshipDefinition


@dataclass(frozen=True, slots=True)
class AgentProfileBundle:
    """Fully parsed built-in agent profile bundle."""

    character: CharacterDefinition
    persona_context: str
    relationship: CharacterRelationshipDefinition


def render_agent_persona_context(bundle: AgentProfileBundle) -> str:
    """Return the prompt-ready persona contract for the built-in agent."""

    return bundle.persona_context.strip()
