"""Tests for save line chat use case."""

from typing import Any

import pytest
from flow_res import is_err

from app.contracts.messages.chat_events import LINE_CHAT_SAVED_TOPIC
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.usecases.chat.save_line_chat import SaveChatHandler, SaveLineChatCommand


@pytest.mark.anyio
async def test_save_line_chat_persists_message(
    uow: IUnitOfWork,
    event_bus: Any,
) -> None:
    """Test that LINE messages are persisted and published."""
    handler = SaveChatHandler(uow, event_bus)

    result = await handler.handle(SaveLineChatCommand(user_id="u1", content="hello"))

    assert not is_err(result)
    assert result.value.id
    event_bus.publish.assert_awaited_once_with(
        LINE_CHAT_SAVED_TOPIC,
        {
            "chat_id": result.value.id,
            "user_id": "u1",
            "content": "hello",
        },
    )

    async with uow:
        raw_query = uow.GetRawChatLogQuery()
        raw_history = await raw_query.get_raw_chat_logs(
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
        assert history.value[-1].message_content.payload["text"] == "hello"
