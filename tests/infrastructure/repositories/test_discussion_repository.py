"""Integration tests for local autonomous discussion persistence."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    DiscussionAuthorKind,
    IncomingDiscussionMessage,
    PrivateReflection,
)
from app.infrastructure.repositories.discussion_repository import (
    SQLAlchemyDiscussionRepository,
)


def _incoming(
    external_id: str, kind: DiscussionAuthorKind
) -> IncomingDiscussionMessage:
    return IncomingDiscussionMessage(
        external_message_id=external_id,
        guild_id="guild",
        channel_id="channel",
        author_external_id=f"author-{external_id}",
        author_display_name="Participant",
        author_kind=kind,
        text=f"message {external_id}",
        occurred_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_repository_deduplicates_public_messages_and_keeps_private_turns(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    observed = await repository.observe(_incoming("1", DiscussionAuthorKind.HUMAN))
    duplicate = await repository.observe(_incoming("1", DiscussionAuthorKind.HUMAN))
    decision = AgentTurnDecision(
        speech_intent="silent",
        texts=[],
        private_reflection=PrivateReflection(observation="No need to repeat."),
    )

    turn = await repository.add_turn(
        trigger_message_id=observed.message_id,
        channel_id=observed.channel_id,
        character_id="agent-1",
        disposition=AgentTurnDisposition.SILENT,
        decision=decision,
    )
    reflections = await repository.recent_reflections(
        character_id="agent-1", channel_id="channel", limit=20
    )

    assert duplicate.is_new is False
    assert duplicate.message_id == observed.message_id
    assert turn.disposition is AgentTurnDisposition.SILENT
    assert reflections == [decision.private_reflection]


@pytest.mark.anyio
async def test_repository_reports_local_publication_activity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    trigger = await repository.observe(_incoming("1", DiscussionAuthorKind.BOT))
    await repository.observe(_incoming("2", DiscussionAuthorKind.BOT))
    decision = AgentTurnDecision(
        speech_intent="speak",
        texts=["hello"],
        private_reflection=PrivateReflection(observation="I should respond."),
    )
    turn = await repository.add_turn(
        trigger_message_id=trigger.message_id,
        channel_id="channel",
        character_id="agent-1",
        disposition=AgentTurnDisposition.PROPOSED,
        decision=decision,
    )
    await repository.update_turn(
        turn_id=turn.turn_id,
        disposition=AgentTurnDisposition.PUBLISHED,
        published_external_message_ids=["3"],
    )

    activity = await repository.activity(
        channel_id="channel",
        character_id="agent-1",
        window_started_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    assert activity.consecutive_bot_messages == 2
    assert activity.published_turns_in_window == 1
    assert activity.last_published_at is not None


@pytest.mark.anyio
async def test_repository_finds_messages_after_pending_trigger(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    occurred_at = datetime.now(UTC)
    trigger = await repository.observe(
        _incoming("trigger", DiscussionAuthorKind.HUMAN).model_copy(
            update={"occurred_at": occurred_at}
        )
    )
    await repository.observe(
        _incoming("newer", DiscussionAuthorKind.BOT).model_copy(
            update={"occurred_at": occurred_at + timedelta(seconds=1)}
        )
    )

    messages = await repository.messages_after(
        guild_id="guild",
        channel_id="channel",
        after_message_id=trigger.message_id,
        limit=1,
    )

    assert [message.external_message_id for message in messages] == ["newer"]
    assert messages[0].is_new is False


@pytest.mark.anyio
async def test_repository_persists_autonomous_topic_and_unifies_reflections(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository = SQLAlchemyDiscussionRepository(session_factory)
    baseline = await repository.observe(
        _incoming("baseline", DiscussionAuthorKind.HUMAN)
    )
    decision = AgentTurnDecision(
        speech_intent="silent",
        texts=[],
        private_reflection=PrivateReflection(observation="No original topic yet."),
    )

    turn = await repository.add_topic_turn(
        guild_id="guild",
        channel_id="channel",
        character_id="agent-1",
        baseline_message_id=baseline.message_id,
        disposition=AgentTurnDisposition.SILENT,
        decision=decision,
    )
    activity = await repository.topic_activity(
        guild_id="guild",
        channel_id="channel",
        character_id="agent-1",
        window_started_at=datetime.now(UTC) - timedelta(days=1),
    )
    reflections = await repository.recent_reflections(
        character_id="agent-1", channel_id="channel", limit=20
    )

    assert turn.baseline_message_id == baseline.message_id
    assert turn.disposition is AgentTurnDisposition.SILENT
    assert activity.latest_message_id == baseline.message_id
    assert activity.last_evaluated_at is not None
    assert reflections == [decision.private_reflection]
