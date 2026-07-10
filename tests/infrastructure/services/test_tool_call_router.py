"""Tests for generated tool-call routing."""

from typing import Any

import pytest
from flow_res import Err, is_err

from app.contracts.messages.chat_events import CHAT_TOOL_REQUESTED_TOPIC
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_call_router import ToolCallRoutingRequest
from app.contracts.ports.tool_call_store import IToolCallStore, ToolCallStoreError
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.tool_call_router import ToolCallRoutingService
from app.infrastructure.services.tool_catalog import StaticToolCatalog
from app.infrastructure.stores.tool_call_store import InMemoryToolCallStore


def _request(*tool_calls: ToolCall) -> ToolCallRoutingRequest:
    return ToolCallRoutingRequest(
        chat_id="chat-1",
        guild_id="guild-1",
        channel_id="channel-1",
        character_id="character-1",
        user_id="user-1",
        chat_type=ChatType.DISCORD,
        tool_calls=list(tool_calls),
    )


@pytest.mark.anyio
async def test_router_assigns_ids_and_routes_every_tool_call(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    store = InMemoryToolCallStore()
    router = ToolCallRoutingService(event_bus, StaticToolCatalog(), store)

    result = await router.route(
        _request(
            ToolCall(tool_name="web_search", arguments={"query": "one"}),
            ToolCall(tool_name="memory.read", arguments={"memory_id": "profile:1"}),
        )
    )

    assert not is_err(result)
    assert len(result.value) == 2
    assert event_bus.publish.await_count == 2
    assert all(
        call.args[0] == CHAT_TOOL_REQUESTED_TOPIC
        for call in event_bus.publish.await_args_list
    )


@pytest.mark.anyio
async def test_router_rejects_unsupported_tool_before_publishing(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    router = ToolCallRoutingService(
        event_bus,
        StaticToolCatalog(),
        InMemoryToolCallStore(),
    )

    result = await router.route(
        _request(ToolCall(tool_name="unsupported", arguments={}))
    )

    assert is_err(result)
    assert "Unsupported tool call" in result.error.message
    event_bus.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_router_surfaces_store_failure(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    store = mocker.Mock(spec=IToolCallStore)
    store.save = mocker.AsyncMock(return_value=Err(ToolCallStoreError("store failed")))
    router = ToolCallRoutingService(event_bus, StaticToolCatalog(), store)

    result = await router.route(
        _request(ToolCall(tool_name="web_search", arguments={"query": "one"}))
    )

    assert is_err(result)
    assert result.error.message == "store failed"
    event_bus.publish.assert_not_awaited()


@pytest.mark.anyio
async def test_router_maps_publish_exception(mocker: Any) -> None:
    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(side_effect=RuntimeError("redis failed"))
    router = ToolCallRoutingService(
        event_bus,
        StaticToolCatalog(),
        InMemoryToolCallStore(),
    )

    result = await router.route(
        _request(ToolCall(tool_name="web_search", arguments={"query": "one"}))
    )

    assert is_err(result)
    assert result.error.message == "Failed to route tool calls"
