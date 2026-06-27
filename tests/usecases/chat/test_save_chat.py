"""Tests for save chat use case."""

from typing import Any

import pytest
from flow_res import is_err

from app.contracts.messages.chat_events import DISCORD_CHAT_SAVED_TOPIC
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.usecases.chat.save_discord_chat import (
    SaveChatHandler,
    SaveDiscordChatCommand,
)


@pytest.mark.anyio
async def test_save_chat_persists_discord_message(
    uow: IUnitOfWork,
    event_bus: Any,
) -> None:
    """Test that incoming DM messages are persisted."""
    handler = SaveChatHandler(uow, event_bus)

    result = await handler.handle(
        SaveDiscordChatCommand(
            user_id="u1",
            guild_id="DM",
            channel_id="123",
            content="hello",
        )
    )

    assert not is_err(result)
    assert result.value.id
    event_bus.publish.assert_awaited_once_with(
        DISCORD_CHAT_SAVED_TOPIC,
        {
            "chat_id": result.value.id,
            "user_id": "u1",
            "guild_id": "DM",
            "channel_id": "123",
        },
    )

    async with uow:
        raw_query = uow.GetRawChatLogQuery()
        raw_history = await raw_query.get_memory_sleep_source_items(
            "u1",
            ChatType.DISCORD,
            limit=10,
        )
        assert not is_err(raw_history)
        assert len(raw_history.value) == 1
        assert raw_history.value[0].user_id == "u1"
        assert raw_history.value[0].role == "user"
        assert raw_history.value[0].message_content["payload"]["text"] == "hello"

        query = uow.GetChatHistoryQuery()
        history = await query.get_recent_history(ChatType.DISCORD, limit=10)
        assert not is_err(history)
        assert history.value.items[-1].role == "user"
        assert history.value.items[-1].content == "hello"
