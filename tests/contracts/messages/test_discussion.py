"""Contract tests for autonomous Discord turn decisions."""

import pytest
from pydantic import ValidationError

from app.contracts.messages.discussion import AgentTurnDecision, PrivateReflection


def test_silent_decision_keeps_private_reflection_without_public_text() -> None:
    decision = AgentTurnDecision(
        speech_intent="silent",
        texts=[],
        private_reflection=PrivateReflection(
            observation="Another participant already covered the point.",
            stance="agree",
            emotion="calm",
            next_intent="wait",
        ),
    )

    assert decision.texts == []
    assert decision.private_reflection.stance == "agree"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "speech_intent": "speak",
            "texts": [],
            "private_reflection": {},
        },
        {
            "speech_intent": "silent",
            "texts": ["This must not be public."],
            "private_reflection": {},
        },
    ],
)
def test_decision_rejects_intent_text_mismatches(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentTurnDecision.model_validate(payload)


def test_private_reflection_rejects_empty_state() -> None:
    with pytest.raises(ValidationError):
        PrivateReflection()
