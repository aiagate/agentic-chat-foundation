"""Use-case tests for internally initiated Discord topics."""

from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    AutonomousTopicActivity,
    DiscussionAuthorKind,
    DiscussionHistoryItem,
    IncomingDiscussionMessage,
    PrivateReflection,
    SentDiscussionMessage,
    TopicStimulus,
)
from app.contracts.ports.discussion import (
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    IDiscussionMessageSender,
)
from app.infrastructure.repositories.discussion_repository import (
    SQLAlchemyDiscussionRepository,
)
from app.usecases.discussion.generate_autonomous_topic import (
    GenerateAutonomousTopicCommand,
    GenerateAutonomousTopicHandler,
)


class _Evaluator(IAutonomousTopicEvaluator):
    def __init__(
        self,
        decision: AgentTurnDecision,
        repository: SQLAlchemyDiscussionRepository | None = None,
    ) -> None:
        self.decision = decision
        self.repository = repository
        self.calls = 0

    async def evaluate(
        self,
        *,
        guild_id: str,
        channel_id: str,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
        stimuli: list[TopicStimulus],
    ) -> AgentTurnDecision:
        del guild_id, channel_id, history, reflections, stimuli
        self.calls += 1
        if self.repository is not None:
            await self.repository.observe(_incoming("arrived-during-evaluation"))
        return self.decision


class _Guard(IAutonomousTopicGuard):
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason

    def eligibility_reason(
        self,
        *,
        activity: AutonomousTopicActivity,
        now: datetime,
    ) -> str | None:
        del activity, now
        return self.reason

    def window_started_at(self, now: datetime) -> datetime:
        return now - timedelta(days=1)


class _Sender(IDiscussionMessageSender):
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, texts: list[str]) -> list[SentDiscussionMessage]:
        self.calls += 1
        return [
            SentDiscussionMessage(
                external_message_id=f"topic-{index}",
                text=text,
                occurred_at=datetime.now(UTC),
            )
            for index, text in enumerate(texts)
        ]


def _decision(intent: Literal["speak", "silent"] = "speak") -> AgentTurnDecision:
    return AgentTurnDecision(
        speech_intent=intent,
        texts=["An original thought."] if intent == "speak" else [],
        private_reflection=PrivateReflection(observation="The room is quiet."),
    )


def _incoming(external_id: str) -> IncomingDiscussionMessage:
    return IncomingDiscussionMessage(
        external_message_id=external_id,
        guild_id="guild",
        channel_id="channel",
        author_external_id="human",
        author_display_name="Human",
        author_kind=DiscussionAuthorKind.HUMAN,
        text="A public message",
        occurred_at=datetime.now(UTC),
    )


def _command(sender: _Sender) -> GenerateAutonomousTopicCommand:
    return GenerateAutonomousTopicCommand(
        guild_id="guild",
        channel_id="channel",
        character_id="agent-1",
        self_external_id="self",
        self_display_name="Agent One",
        sender=sender,
    )


@pytest.mark.anyio
async def test_ineligible_topic_opportunity_skips_llm(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(_decision())
    sender = _Sender()
    handler = GenerateAutonomousTopicHandler(
        repository, repository, evaluator, _Guard("channel_not_idle")
    )

    result = await handler.handle(_command(sender))

    assert is_ok(result)
    assert result.value is None
    assert evaluator.calls == 0
    assert sender.calls == 0


@pytest.mark.anyio
async def test_silent_autonomous_topic_is_persisted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(_decision("silent"))
    sender = _Sender()
    handler = GenerateAutonomousTopicHandler(
        repository, repository, evaluator, _Guard()
    )

    result = await handler.handle(_command(sender))

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.SILENT
    assert result.value.private_reflection is not None
    assert sender.calls == 0


@pytest.mark.anyio
async def test_autonomous_topic_is_published_and_added_to_public_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    sender = _Sender()
    handler = GenerateAutonomousTopicHandler(
        repository, repository, _Evaluator(_decision()), _Guard()
    )

    result = await handler.handle(_command(sender))
    history = await repository.latest_history(
        guild_id="guild", channel_id="channel", limit=10
    )

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.PUBLISHED
    assert result.value.published_external_message_ids == ["topic-0"]
    assert [item.text for item in history] == ["An original thought."]


@pytest.mark.anyio
async def test_new_public_message_supersedes_autonomous_topic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    await repository.observe(
        _incoming("baseline").model_copy(
            update={"occurred_at": datetime.now(UTC) - timedelta(hours=1)}
        )
    )
    sender = _Sender()
    evaluator = _Evaluator(_decision(), repository)
    handler = GenerateAutonomousTopicHandler(
        repository, repository, evaluator, _Guard()
    )

    result = await handler.handle(_command(sender))

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.SUPERSEDED
    assert result.value.failure_reason is not None
    assert result.value.failure_reason.startswith("superseded_by_newer_message:")
    assert sender.calls == 0
