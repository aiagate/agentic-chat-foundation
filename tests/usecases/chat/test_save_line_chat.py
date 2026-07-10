"""Tests for save line chat use case."""

from typing import Any, cast

import pytest
from flow_res import is_err
from sqlalchemy import select

from app.contracts.messages.chat_events import LINE_CHAT_SAVED_TOPIC
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.orm_models.outbox_message_orm import OutboxMessageORM
from app.usecases.chat.save_line_chat import SaveLineChatCommand, SaveLineChatHandler


@pytest.mark.anyio
async def test_save_line_chat_persists_message(
    uow: IUnitOfWork,
) -> None:
    """Test that LINE messages are persisted and published."""
    handler = SaveLineChatHandler(uow)

    result = await handler.handle(SaveLineChatCommand(user_id="u1", content="hello"))

    assert not is_err(result)
    assert result.value.id
    async with uow:
        session = cast(Any, uow)._session
        outbox_result = await session.execute(select(OutboxMessageORM))
        outbox_message = outbox_result.scalar_one()
        assert outbox_message.topic == LINE_CHAT_SAVED_TOPIC
        assert outbox_message.payload["chat_id"] == result.value.id
        assert outbox_message.payload["event_id"] == outbox_message.id

        raw_query = uow.GetRawChatLogQuery()
        raw_history = await raw_query.get_memory_sleep_source_items(
            "u1",
            ChatType.LINE,
            limit=10,
        )
        assert not is_err(raw_history)
        assert len(raw_history.value) == 1
        assert raw_history.value[0].user_id == "u1"
        assert raw_history.value[0].role == "user"
        assert raw_history.value[0].message_content["payload"]["text"] == "hello"

        query = uow.GetChatHistoryQuery()
        history = await query.get_recent_history(ChatType.LINE, limit=10)
        assert not is_err(history)
        assert history.value.items[-1].role == "user"
        assert history.value.items[-1].content == "hello"
