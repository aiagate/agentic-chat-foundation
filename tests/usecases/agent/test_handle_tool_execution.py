"""Tests for the generic tool execution handler."""

from typing import Any

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.tool_contracts import ToolCall, ToolExecutionResult
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutorError,
)
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.services.tool_catalog import StaticToolCatalog
from app.infrastructure.stores.tool_call_store import InMemoryToolCallStore
from app.infrastructure.stores.tool_execution_lock import InMemoryToolExecutionLock
from app.infrastructure.stores.tool_result_store import InMemoryToolResultStore
from app.usecases.agent.handle_tool_execution import (
    HandleToolExecutionCommand,
    HandleToolExecutionHandler,
)

CHARACTER_ID = "shirasagi-reina"


def _handler(
    event_bus: IEventBus,
    tool_executor: IToolExecutor,
    tool_call_store: InMemoryToolCallStore,
    uow: IUnitOfWork,
) -> HandleToolExecutionHandler:
    return HandleToolExecutionHandler(
        event_bus,
        tool_executor,
        tool_call_store,
        InMemoryToolExecutionLock(),
        StaticToolCatalog(),
        InMemoryToolResultStore(),
        uow,
    )


@pytest.mark.anyio
async def test_handle_tool_execution_publishes_completion(
    mocker: Any,
    uow: IUnitOfWork,
) -> None:
    """The handler should publish tool completion for successful execution."""

    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock(
        return_value=Ok(
            ToolExecutionResult(
                tool_name="line.send",
                status="ok",
                result={"content_count": 1},
            )
        )
    )
    tool_call_store = InMemoryToolCallStore()
    await tool_call_store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
            tool_name="line.send",
            arguments={"contents": ["hello"]},
        )
    )

    handler = _handler(event_bus, tool_executor, tool_call_store, uow)
    result = await handler.handle(
        HandleToolExecutionCommand(
            chat_id="chat-1",
            tool_call_id="tool-1",
            user_id="u1",
            chat_type=ChatType.LINE,
            tool_name="line.send",
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    tool_executor.execute.assert_not_awaited()
    publish_mock = event_bus.publish
    assert publish_mock.await_count == 2
    reply_topic, reply_payload = publish_mock.await_args_list[0].args
    assert reply_topic == "chat.line.reply_ready"
    assert reply_payload["contents"] == ["hello"]
    topic, payload = publish_mock.await_args_list[1].args
    assert topic == "chat.tool.completed"
    assert payload["status"] == "ok"
    assert payload["tool_name"] == "line.send"
    assert payload["result"]["content_count"] == 1

    async with uow:
        history_result = await uow.GetChatHistoryQuery().get_recent_history(
            ChatType.LINE,
            user_id="u1",
        )
    assert not is_err(history_result)
    assert [item.role for item in history_result.value.items] == ["assistant"]
    assert history_result.value.items[0].content == "hello"


@pytest.mark.anyio
async def test_discord_send_persists_in_current_scope(
    mocker: Any,
    uow: IUnitOfWork,
) -> None:
    """A Discord send tool persists text in the current channel."""

    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock()
    tool_call_store = InMemoryToolCallStore()
    await tool_call_store.save(
        ToolCall(
            tool_call_id="tool-post",
            character_id=CHARACTER_ID,
            tool_name="discord.send",
            arguments={"contents": ["hello", "world"]},
        )
    )
    handler = _handler(event_bus, tool_executor, tool_call_store, uow)

    result = await handler.handle(
        HandleToolExecutionCommand(
            chat_id="chat-1",
            tool_call_id="tool-post",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            tool_name="discord.send",
            character_id=CHARACTER_ID,
            guild_id="guild-1",
            channel_id="123",
        )
    )

    assert not is_err(result)
    assert result.value.result == {"content_count": 2}
    tool_executor.execute.assert_not_awaited()
    async with uow:
        history_result = await uow.GetChatHistoryQuery().get_recent_history(
            ChatType.DISCORD,
            user_id="u1",
            guild_id="guild-1",
            channel_id="123",
        )
    assert not is_err(history_result)
    assert history_result.value.items[0].content == "hello\n\nworld"


@pytest.mark.anyio
async def test_handle_tool_execution_surfaces_executor_error(
    mocker: Any,
    uow: IUnitOfWork,
) -> None:
    """The handler should publish an error completion when execution fails."""

    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock(
        return_value=Err(ToolExecutorError("boom"))
    )
    tool_call_store = InMemoryToolCallStore()
    await tool_call_store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
            tool_name="web_search",
            arguments={"query": "hello"},
        )
    )

    handler = _handler(event_bus, tool_executor, tool_call_store, uow)
    result = await handler.handle(
        HandleToolExecutionCommand(
            chat_id="chat-1",
            tool_call_id="tool-1",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            tool_name="web_search",
            character_id=CHARACTER_ID,
        )
    )

    assert is_err(result)
    publish_mock = event_bus.publish
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == "chat.tool.completed"
    assert payload["status"] == "error"
    assert payload["error"] == "boom"
    assert payload["error_code"] == "tool_execution_error"


@pytest.mark.anyio
async def test_handle_tool_execution_reports_missing_tool_call(
    mocker: Any,
    uow: IUnitOfWork,
) -> None:
    """The handler should fail before execution when the stored tool call is absent."""

    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock()
    tool_call_store = InMemoryToolCallStore()

    handler = _handler(event_bus, tool_executor, tool_call_store, uow)
    result = await handler.handle(
        HandleToolExecutionCommand(
            chat_id="chat-1",
            tool_call_id="missing-tool",
            user_id="u1",
            chat_type=ChatType.LINE,
            tool_name="line.send",
            character_id=CHARACTER_ID,
        )
    )

    assert is_err(result)
    tool_executor.execute.assert_not_awaited()
    publish_mock = event_bus.publish
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == "chat.tool.completed"
    assert payload["status"] == "error"
    assert payload["error_code"] == "tool_call_not_found"


@pytest.mark.anyio
async def test_handle_tool_execution_skips_duplicate_execution(
    mocker: Any,
    uow: IUnitOfWork,
) -> None:
    """Duplicate tool events should not execute or publish completion twice."""

    event_bus = mocker.Mock(spec=IEventBus)
    event_bus.publish = mocker.AsyncMock(return_value=None)
    tool_executor = mocker.Mock(spec=IToolExecutor)
    tool_executor.execute = mocker.AsyncMock(
        return_value=Ok(
            ToolExecutionResult(
                tool_name="web_search",
                status="ok",
                result={"retrieved_context": True},
            )
        )
    )
    tool_call_store = InMemoryToolCallStore()
    await tool_call_store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
            tool_name="web_search",
            arguments={"query": "hello"},
        )
    )
    handler = _handler(event_bus, tool_executor, tool_call_store, uow)
    command = HandleToolExecutionCommand(
        chat_id="chat-1",
        tool_call_id="tool-1",
        character_id=CHARACTER_ID,
        user_id="u1",
        chat_type=ChatType.DISCORD,
        tool_name="web_search",
    )

    first = await handler.handle(command)
    second = await handler.handle(command)

    assert not is_err(first)
    assert not is_err(second)
    assert second.value.result == {"duplicate": True}
    tool_executor.execute.assert_awaited_once()
    event_bus.publish.assert_awaited_once()
