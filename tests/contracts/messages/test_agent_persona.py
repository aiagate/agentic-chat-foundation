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

    assert bundle.character.character_id == "test-agent"
    assert bundle.relationship_entity_id == "relationship:test-agent"
    assert bundle.relationship_entity_label == "テストエージェントとの関係"
    assert bundle.relationship_entity_type == "relationship"
    assert bundle.relationship_tag == "agent-growth"
    assert bundle.relationship_defaults.trust_score == 0.0
    assert bundle.relationship_defaults.warmth_score == 0.0
    assert bundle.relationship_defaults.stage == 0


def _bundle() -> AgentProfileBundle:
    return AgentProfileBundle(
        profile=MemoryProfile(
            user_id="ai",
            display_name="テストエージェント",
            summary="落ち着いた応対をするテスト用の人格。",
            traits=["寡黙", "理性的"],
            preferences=["静かな場所"],
        ),
        character=CharacterDefinition(
            character_id="test-agent",
            display_name="テストエージェント",
            relationship_entity_id="relationship:test-agent",
            relationship_entity_label="テストエージェントとの関係",
        ),
        persona_context="\n".join(
            [
                "# Persona Contract",
                "",
                "- test persona",
            ]
        ),
        communication_style=("落ち着いて話す",),
        known_constraints=("AI と名乗らない",),
        atmosphere=("静かな夜",),
        behavior=("相手の意図を先にくむ",),
        relationship_entity_id="relationship:test-agent",
        relationship_entity_label="テストエージェントとの関係",
        relationship_entity_type="relationship",
        relationship_tag="agent-growth",
        relationship_defaults=RelationshipDefaults(),
        relationship=("最小限の自己開示",),
        fallback=("季節感のある料理を選ぶ",),
        memory_reading_rules=("Bundle is read from memory files.",),
    )
