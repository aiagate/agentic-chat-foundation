"""Tests for tool completion event publication."""

from typing import Any

import pytest

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import CHAT_TOOL_COMPLETED_TOPIC
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_completion_notifier import ToolCompletionNotification
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.tool_completion_notifier import (
    EventBusToolCompletionNotifier,
)


@pytest.mark.anyio
async def test_notifier_publishes_normalized_success_payload(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    notifier = EventBusToolCompletionNotifier(event_bus)

    await notifier.notify(
        ToolCompletionNotification(
            chat_id="chat-1",
            chat_type=ChatType.DISCORD,
            user_id="user-1",
            tool_name="web_search",
            continuation="reenter",
            status="ok",
            result={"result_count": 1},
            guild_id="guild-1",
            channel_id="channel-1",
            agent_context=AgentEnvelope(
                character_id="character-1",
                tool_call_id="tool-1",
            ),
        )
    )

    event_bus.publish.assert_awaited_once()
    topic, payload = event_bus.publish.await_args.args
    assert topic == CHAT_TOOL_COMPLETED_TOPIC
    assert payload["status"] == "ok"
    assert payload["continuation"] == "reenter"
    assert payload["tool_call_id"] == "tool-1"
    assert payload["result"] == {"result_count": 1}


@pytest.mark.anyio
async def test_notifier_publishes_normalized_error_payload(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    notifier = EventBusToolCompletionNotifier(event_bus)

    await notifier.notify(
        ToolCompletionNotification(
            chat_id="chat-1",
            chat_type=ChatType.LINE,
            user_id="user-1",
            tool_name="line.send",
            continuation="terminal",
            status="error",
            error="send failed",
            error_code="tool_execution_error",
        )
    )

    _, payload = event_bus.publish.await_args.args
    assert payload["status"] == "error"
    assert payload["continuation"] == "terminal"
    assert payload["error"] == "send failed"
    assert payload["error_code"] == "tool_execution_error"
