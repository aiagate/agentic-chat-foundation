"""Use-case tests for one independent Discord discussion bot."""

from datetime import UTC, datetime, timedelta

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    DiscussionActivity,
    DiscussionAuthorKind,
    DiscussionHistoryItem,
    IncomingDiscussionMessage,
    ObservedDiscussionMessage,
    PrivateReflection,
    SentDiscussionMessage,
)
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IDiscussionMessageSender,
    ILocalSpeechGuard,
)
from app.infrastructure.repositories.discussion_repository import (
    SQLAlchemyDiscussionRepository,
)
from app.usecases.discussion.process_discussion_message import (
    ProcessDiscussionMessageCommand,
    ProcessDiscussionMessageHandler,
)


class _Evaluator(IAgentTurnEvaluator):
    def __init__(self, decision: AgentTurnDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def evaluate(
        self,
        *,
        message: ObservedDiscussionMessage,
        history: list[DiscussionHistoryItem],
        reflections: list[PrivateReflection],
    ) -> AgentTurnDecision:
        del message, history, reflections
        self.calls += 1
        return self.decision


class _Guard(ILocalSpeechGuard):
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason

    def withholding_reason(
        self,
        *,
        message: ObservedDiscussionMessage,
        activity: DiscussionActivity,
        now: datetime,
    ) -> str | None:
        del message, activity, now
        return self.reason

    def window_started_at(self, now: datetime) -> datetime:
        return now


class _Sender(IDiscussionMessageSender):
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, texts: list[str]) -> list[SentDiscussionMessage]:
        self.calls += 1
        return [
            SentDiscussionMessage(
                external_message_id=f"sent-{index}",
                text=text,
                occurred_at=datetime.now(UTC),
            )
            for index, text in enumerate(texts)
        ]


def _incoming(external_id: str) -> IncomingDiscussionMessage:
    return IncomingDiscussionMessage(
        external_message_id=external_id,
        guild_id="guild",
        channel_id="channel",
        author_external_id="other-bot",
        author_display_name="Other Bot",
        author_kind=DiscussionAuthorKind.BOT,
        text="What do you think?",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_silent_decision_is_persisted_without_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(
        AgentTurnDecision(
            speech_intent="silent",
            texts=[],
            private_reflection=PrivateReflection(observation="Nothing to add."),
        )
    )
    sender = _Sender()
    handler = ProcessDiscussionMessageHandler(repository, evaluator, _Guard())

    result = await handler.handle(
        ProcessDiscussionMessageCommand(
            message=_incoming("incoming-1"),
            character_id="agent-1",
            self_external_id="self",
            self_display_name="Self Bot",
            sender=sender,
        )
    )

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.SILENT
    assert evaluator.calls == 1
    assert sender.calls == 0


@pytest.mark.anyio
async def test_public_decision_is_withheld_only_after_llm_evaluation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(
        AgentTurnDecision(
            speech_intent="speak",
            texts=["I have one point."],
            private_reflection=PrivateReflection(observation="Useful addition."),
        )
    )
    sender = _Sender()
    handler = ProcessDiscussionMessageHandler(
        repository, evaluator, _Guard("local_publication_cooldown")
    )

    result = await handler.handle(
        ProcessDiscussionMessageCommand(
            message=_incoming("incoming-2"),
            character_id="agent-1",
            self_external_id="self",
            self_display_name="Self Bot",
            sender=sender,
        )
    )

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.WITHHELD
    assert evaluator.calls == 1
    assert sender.calls == 0


@pytest.mark.anyio
async def test_public_decision_is_sent_and_recorded_locally(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(
        AgentTurnDecision(
            speech_intent="speak",
            texts=["First", "Second"],
            private_reflection=PrivateReflection(observation="Two short points."),
        )
    )
    sender = _Sender()
    handler = ProcessDiscussionMessageHandler(repository, evaluator, _Guard())

    result = await handler.handle(
        ProcessDiscussionMessageCommand(
            message=_incoming("incoming-3"),
            character_id="agent-1",
            self_external_id="self",
            self_display_name="Self Bot",
            sender=sender,
        )
    )

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.PUBLISHED
    assert result.value.published_external_message_ids == ["sent-0", "sent-1"]
    assert sender.calls == 1


@pytest.mark.anyio
async def test_pending_public_decision_is_superseded_by_newer_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    evaluator = _Evaluator(
        AgentTurnDecision(
            speech_intent="speak",
            texts=["My original answer."],
            private_reflection=PrivateReflection(observation="I could answer."),
        )
    )
    sender = _Sender()
    occurred_at = datetime.now(UTC)
    trigger = _incoming("pending-trigger").model_copy(
        update={"occurred_at": occurred_at}
    )
    newer = _incoming("newer-answer").model_copy(
        update={"occurred_at": occurred_at + timedelta(seconds=1)}
    )
    await repository.observe(newer)
    handler = ProcessDiscussionMessageHandler(repository, evaluator, _Guard())

    result = await handler.handle(
        ProcessDiscussionMessageCommand(
            message=trigger,
            character_id="agent-1",
            self_external_id="self",
            self_display_name="Self Bot",
            sender=sender,
        )
    )

    assert is_ok(result)
    assert result.value is not None
    assert result.value.disposition is AgentTurnDisposition.SUPERSEDED
    assert result.value.failure_reason is not None
    assert result.value.failure_reason.startswith("superseded_by_newer_message:")
    assert sender.calls == 0
