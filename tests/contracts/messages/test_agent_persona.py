"""Tests for the shared agent profile bundle and persona prompt."""

from app.contracts.messages.agent_profile import (
    AgentProfileBundle,
    render_agent_persona_context,
)
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.relationship import RelationshipSignalKind
from tests._relationship_fixture import relationship_definition


def test_render_agent_persona_context_returns_bundle_text() -> None:
    """The persona prompt should come directly from the bundle payload."""

    bundle = _bundle()

    assert render_agent_persona_context(bundle) == bundle.persona_context


def test_agent_profile_bundle_exposes_relationship_configuration() -> None:
    """Relationship metadata should stay attached to the profile bundle."""

    bundle = _bundle()

    assert bundle.character.character_id == "jondue"
    assert bundle.relationship.schema_version == 1
    assert len(bundle.relationship.stages) == 8
    assert bundle.relationship.signal_deltas[RelationshipSignalKind.POSITIVE] == 1


def _bundle() -> AgentProfileBundle:
    return AgentProfileBundle(
        character=CharacterDefinition(character_id="jondue"),
        persona_context="\n".join(
            [
                "# Persona Contract",
                "",
                "- test persona",
            ]
        ),
        relationship=relationship_definition(),
    )
