"""Tests for canonical agent-turn event publication."""

from typing import Any

import pytest

from app.contracts.ports.event_bus import IEventBus
from app.domain.value_objects.chat_type import ChatType
from app.usecases.agent.request_agent_turn import (
    RequestAgentTurnCommand,
    RequestAgentTurnHandler,
)


@pytest.mark.anyio
async def test_request_agent_turn_publishes_canonical_event(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    handler = RequestAgentTurnHandler(event_bus)

    await handler.handle(
        RequestAgentTurnCommand(
            chat_id="chat-1",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            guild_id="DM",
            channel_id="123",
            character_id="shirasagi-reina",
        )
    )

    topic, payload = event_bus.publish.await_args.args
    assert topic == "chat.agent_turn.requested"
    assert payload["character_id"] == "shirasagi-reina"
    assert payload["channel_id"] == "123"
