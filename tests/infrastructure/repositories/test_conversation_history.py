"""Integration tests for canonical conversation history persistence."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.conversation import ConversationResult, IncomingMessage
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.repositories.conversation_history import (
    SQLAlchemyConversationHistory,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork


@pytest.mark.anyio
async def test_history_deduplicates_external_message_and_saves_assistant_after_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    history = SQLAlchemyConversationHistory(SQLAlchemyUnitOfWork(session_factory))
    message = IncomingMessage(
        channel="discord",
        external_conversation_id="channel-1",
        external_participant_id="user-1",
        text="hello",
        external_message_id="provider-1",
        occurred_at=datetime.now(UTC),
    )

    first = await history.append(message)
    duplicate = await history.append(message)
    await history.append_assistant(
        first,
        ConversationResult(
            message_id=first.message_id,
            conversation_id=first.conversation_id,
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
