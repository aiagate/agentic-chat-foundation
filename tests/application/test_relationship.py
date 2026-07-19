"""Tests for application-owned relationship behavior selection."""

import hashlib

from app.application.relationship import (
    render_relationship_behavior,
    select_relationship_behavior,
)
from app.contracts.messages.relationship import RelationshipStateView
from app.domain.aggregates.character_relationship import RelationshipStageId
from tests._relationship_fixture import relationship_definition


def test_relationship_behavior_is_deterministic_and_matches_weight_bucket() -> None:
    definition = relationship_definition()
    state = RelationshipStateView(
        character_id="shirasagi-reina",
        user_id="user-1",
        affection=41,
        stage_id=RelationshipStageId.AFFECTIONATE,
        version=2,
    )
    message_id = "message-1"

    first = select_relationship_behavior(
        definition=definition, state=state, message_id=message_id
    )
    second = select_relationship_behavior(
        definition=definition, state=state, message_id=message_id
    )

    seed = "\x1f".join((state.character_id, state.user_id, message_id, "1")).encode()
    bucket = int.from_bytes(hashlib.sha256(seed).digest(), "big") % 10
    expected_id = "neutral" if bucket < 4 else f"cue-{((bucket - 4) // 2) + 1}"
    assert first == second
    assert first.behavior_id == expected_id


def test_rendered_behavior_exposes_only_selected_context() -> None:
    state = RelationshipStateView(
        character_id="kurose-marina",
        user_id="user-1",
        affection=100,
        stage_id=RelationshipStageId.DEVOTED,
        version=3,
    )
    directive = select_relationship_behavior(
        definition=relationship_definition(),
        state=state,
        message_id="message-2",
    )

    rendered = render_relationship_behavior(directive)

    assert directive.instruction in rendered
    assert "100" not in rendered
    assert "devoted" not in rendered
    assert "cue-1" not in rendered
