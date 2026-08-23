"""Integration tests for canonical conversation history persistence."""

from datetime import UTC, datetime
from typing import TypedDict

import pytest
from flow_res import is_ok
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.conversation import ConversationResult, IncomingMessage
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.repositories.conversation_history import (
    SQLAlchemyConversationHistory,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWorkFactory


class _MessageValues(TypedDict):
    character_id: str
    channel: str
    user_id: str
    external_conversation_id: str
    external_participant_id: str
    external_message_id: str
    role: str
    message_content: dict[str, object]
    channel_metadata: dict[str, object]


@pytest.mark.anyio
async def test_history_deduplicates_external_message_and_saves_assistant_after_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    history = SQLAlchemyConversationHistory(
        SQLAlchemyUnitOfWorkFactory(session_factory), "shirasagi-reina"
    )
    message = IncomingMessage(
        channel="discord",
        external_conversation_id="channel-1",
        external_participant_id="user-1",
        text="hello",
        external_message_id="provider-1",
        occurred_at=datetime.now(UTC),
    )

    first = await history.append(message, user_id="01JUSER000000000000000001")
    duplicate = await history.append(message, user_id="01JUSER000000000000000001")
    await history.append_assistant(
        first,
        ConversationResult(
            message_id=first.message_id,
            external_conversation_id=first.external_conversation_id,
            channel=first.channel,
            contents=("hi",),
        ),
    )

    assert first.is_new is True
    assert duplicate.is_new is False
    assert duplicate.message_id == first.message_id
    async with session_factory() as session:
        rows = list((await session.execute(select(ChatORM))).scalars().all())
    assert [(row.role, row.external_message_id) for row in rows] == [
        ("user", "provider-1"),
        ("assistant", None),
    ]
    assert rows[0].message_content == {
        "type": "TEXT",
        "payload": {"texts": ["hello"]},
    }
    assert rows[0].accepted_sequence > 0
    assert rows[1].message_content == {
        "type": "TEXT",
        "payload": {"texts": ["hi"]},
    }
    assert rows[1].accepted_sequence > rows[0].accepted_sequence


@pytest.mark.anyio
async def test_record_repository_deduplicates_at_insert_boundary(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A duplicate is reported as existing even when pre-checks are bypassed."""

    factory = SQLAlchemyUnitOfWorkFactory(session_factory)
    values: _MessageValues = {
        "character_id": "shirasagi-reina",
        "channel": "discord",
        "user_id": "01JUSER000000000000000001",
        "external_conversation_id": "channel-1",
        "external_participant_id": "user-1",
        "external_message_id": "provider-race-1",
        "role": "user",
        "message_content": {
            "type": "TEXT",
            "payload": {"texts": ["hello"]},
        },
        "channel_metadata": {},
    }
    async with factory.create() as uow:
        first = await uow.GetChatRecordRepository().add_message(**values)
        assert is_ok(first)
        await uow.commit()

    async with factory.create() as uow:
        duplicate = await uow.GetChatRecordRepository().add_message(**values)
        assert is_ok(duplicate)
        assert duplicate.value.is_new is False
        assert duplicate.value.message_id == first.value.message_id
        await uow.commit()


@pytest.mark.anyio
async def test_history_rejects_external_id_owned_by_another_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An external event id must never be accepted under another owner."""

    history = SQLAlchemyConversationHistory(
        SQLAlchemyUnitOfWorkFactory(session_factory), "shirasagi-reina"
    )
    message = IncomingMessage(
        channel="discord",
        external_conversation_id="channel-1",
        external_participant_id="user-1",
        text="hello",
        external_message_id="provider-owner-1",
        occurred_at=datetime.now(UTC),
    )
    await history.append(message, user_id="01JUSER000000000000000001")

    with pytest.raises(ValueError, match="owned by another user"):
        await history.append(message, user_id="01JUSER000000000000000002")
