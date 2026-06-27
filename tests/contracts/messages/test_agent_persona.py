"""Tests for the shared agent profile bundle and persona prompt."""

from app.contracts.messages.agent_profile import (
    AgentProfileBundle,
    render_agent_persona_context,
)
from app.contracts.messages.character_definition import (
    CharacterDefinition,
    RelationshipDefaults,
)
from app.contracts.messages.memory_context import MemoryProfile


def test_render_agent_persona_context_returns_bundle_text() -> None:
    """The persona prompt should come directly from the bundle payload."""

    bundle = _bundle()

    assert render_agent_persona_context(bundle) == bundle.persona_context


def test_agent_profile_bundle_exposes_relationship_configuration() -> None:
    """Relationship metadata should stay attached to the profile bundle."""

    bundle = _bundle()

    assert bundle.character.character_id == "jondue"
    assert bundle.relationship_entity_id == "relationship:jondue"
    assert bundle.relationship_entity_label == "Relationship with Jon Due"
    assert bundle.relationship_entity_type == "relationship"
    assert bundle.relationship_tag == "agent-growth"
    assert bundle.relationship_defaults.trust_score == 0.0
    assert bundle.relationship_defaults.warmth_score == 0.0
    assert bundle.relationship_defaults.stage == 0


def _bundle() -> AgentProfileBundle:
    return AgentProfileBundle(
        profile=MemoryProfile(
            user_id="ai",
        ),
        character=CharacterDefinition(
            character_id="jondue",
            relationship_entity_id="relationship:jondue",
            relationship_entity_label="Relationship with Jon Due",
        ),
        persona_context="\n".join(
            [
                "# Persona Contract",
                "",
                "- test persona",
            ]
        ),
        relationship_entity_id="relationship:jondue",
        relationship_entity_label="Relationship with Jon Due",
        relationship_entity_type="relationship",
        relationship_tag="agent-growth",
        relationship_defaults=RelationshipDefaults(),
    )
