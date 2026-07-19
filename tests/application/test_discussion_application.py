"""Tests for local autonomous discussion evaluation and speech limits."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from flow_res import Ok, Result

from app.application.discussion import (
    LocalAutonomousTopicGuard,
    LocalAutonomousTopicGuardSettings,
    LocalSpeechGuard,
    LocalSpeechGuardSettings,
    StructuredAgentTurnEvaluator,
    StructuredAutonomousTopicEvaluator,
)
from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.discussion import (
    AutonomousTopicActivity,
    DiscussionActivity,
    DiscussionAuthorKind,
    DiscussionHistoryItem,
    ObservedDiscussionMessage,
)
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from tests._relationship_fixture import relationship_definition


class _ProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        character = CharacterDefinition(character_id="agent-1")
        return AgentProfileBundle(
            character=character,
            persona_context="You are Agent One.",
            relationship=relationship_definition(),
        )


class _DecisionAI(IAIService):
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.history: list[ChatHistoryItem] | None = None
        self.system_instruction: str | None = None

    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        self.prompt = prompt
        self.history = history
        self.system_instruction = system_instruction
        del tool_definitions, tool_results
        return Ok(
            GeneratedContent(
                contents=[
                    """{
                      "speech_intent": "silent",
                      "texts": [],
                      "private_reflection": {
                        "observation": "covered",
                        "stance": "agree",
                        "emotion": "calm",
                        "next_intent": "wait",
                        "open_question": null
                      }
                    }"""
                ]
            )
        )


def _message(*, mentioned_self: bool = False) -> ObservedDiscussionMessage:
    return ObservedDiscussionMessage(
        message_id="01J00000000000000000000000",
        external_message_id="100",
        guild_id="guild",
        channel_id="channel",
        author_external_id="user",
        author_display_name="User",
        author_kind=DiscussionAuthorKind.HUMAN,
        text="What do you think?",
        mentioned_self=mentioned_self,
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_evaluator_parses_private_silent_decision() -> None:
    ai_service = _DecisionAI()
    evaluator = StructuredAgentTurnEvaluator(ai_service, _ProfileService())

    decision = await evaluator.evaluate(message=_message(), history=[], reflections=[])

    assert decision.speech_intent == "silent"
    assert decision.private_reflection.observation == "covered"
    assert ai_service.history == []


@pytest.mark.anyio
async def test_evaluator_passes_multi_party_history_as_structured_json() -> None:
    ai_service = _DecisionAI()
    evaluator = StructuredAgentTurnEvaluator(ai_service, _ProfileService())
    occurred_at = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    history = [
        DiscussionHistoryItem(
            message_id="history-message",
            external_message_id="discord-history",
            author_external_id="bot-2",
            author_display_name="Other Bot",
            author_kind=DiscussionAuthorKind.BOT,
            text="Earlier message",
            occurred_at=occurred_at,
        )
    ]

    await evaluator.evaluate(message=_message(), history=history, reflections=[])

    assert ai_service.prompt is not None
    context = json.loads(ai_service.prompt)
    assert ai_service.history == []
    assert context["context_type"] == "discord_discussion_turn"
    assert context["latest_message_id"] == "01J00000000000000000000000"
    assert context["messages"][0]["author"] == {
        "external_id": "bot-2",
        "display_name": "Other Bot",
        "kind": "bot",
    }
    assert context["messages"][0]["text"] == "Earlier message"
    assert context["messages"][1]["author"]["display_name"] == "User"
    assert context["messages"][1]["text"] == "What do you think?"
    assert "[Other Bot]" not in ai_service.prompt


@pytest.mark.anyio
async def test_autonomous_topic_evaluator_uses_empty_future_stimuli_boundary() -> None:
    ai_service = _DecisionAI()
    evaluator = StructuredAutonomousTopicEvaluator(ai_service, _ProfileService())

    decision = await evaluator.evaluate(
        guild_id="guild",
        channel_id="channel",
        history=[],
        reflections=[],
        stimuli=[],
    )

    assert decision.speech_intent == "silent"
    assert ai_service.prompt is not None
    context = json.loads(ai_service.prompt)
    assert context["context_type"] == "autonomous_topic_generation"
    assert context["stimuli"] == []
    assert ai_service.system_instruction is not None
    assert "Never invent current news" in ai_service.system_instruction


def test_guard_applies_limits_after_evaluation() -> None:
    guard = LocalSpeechGuard(LocalSpeechGuardSettings())
    now = datetime.now(UTC)

    assert (
        guard.withholding_reason(
            message=_message(),
            activity=DiscussionActivity(
                consecutive_bot_messages=8,
                published_turns_in_window=0,
            ),
            now=now,
        )
        == "consecutive_bot_message_limit"
    )
    assert (
        guard.withholding_reason(
            message=_message(mentioned_self=True),
            activity=DiscussionActivity(
                consecutive_bot_messages=0,
                last_published_at=now - timedelta(seconds=1),
                published_turns_in_window=0,
            ),
            now=now,
        )
        is None
    )


def test_autonomous_topic_guard_requires_idle_channel_and_local_cadence() -> None:
    guard = LocalAutonomousTopicGuard(LocalAutonomousTopicGuardSettings())
    now = datetime.now(UTC)

    assert (
        guard.eligibility_reason(
            activity=AutonomousTopicActivity(
                latest_message_at=now - timedelta(minutes=5),
                published_topics_in_window=0,
            ),
            now=now,
        )
        == "channel_not_idle"
    )
    assert (
        guard.eligibility_reason(
            activity=AutonomousTopicActivity(
                latest_message_at=now - timedelta(hours=1),
                last_evaluated_at=now - timedelta(minutes=5),
                published_topics_in_window=0,
            ),
            now=now,
        )
        == "topic_evaluation_cooldown"
    )
    assert (
        guard.eligibility_reason(
            activity=AutonomousTopicActivity(
                latest_message_at=now - timedelta(hours=1),
                last_evaluated_at=now - timedelta(hours=1),
                published_topics_in_window=3,
            ),
            now=now,
        )
        == "topic_publication_rate_limit"
    )
