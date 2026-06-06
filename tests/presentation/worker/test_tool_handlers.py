"""Tests for generic worker tool handlers."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_med import Mediator

from app.presentation.worker.handlers.tool_handlers import (
    on_chat_tool_completed,
    on_chat_tool_requested,
)
from app.usecases.agent.handle_tool_execution import HandleToolExecutionCommand
from app.usecases.agent.run_agent_turn import RunAgentTurnQuery


@pytest.mark.anyio
async def test_chat_tool_requested_dispatches_execution(
    mocker: Any,
) -> None:
    """Test that generic tool requests dispatch the execution usecase."""

    send_async = cast(Any, AsyncMock(return_value=None))
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_requested(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "chat_type": "DISCORD",
            "character_id": "shirasagi-reina",
            "tool_call_id": "tool-1",
            "tool_name": "web_search",
        }
    )

    send_async.assert_awaited_once()
    request = send_async.await_args.args[0]
    assert isinstance(request, HandleToolExecutionCommand)
    assert request.tool_call_id == "tool-1"
    assert request.tool_name == "web_search"


@pytest.mark.anyio
async def test_chat_tool_requested_dispatches_memory_search_execution(
    mocker: Any,
) -> None:
    """Test that generic memory search tool requests dispatch execution."""

    send_async = cast(Any, AsyncMock(return_value=None))
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_requested(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "chat_type": "DISCORD",
            "character_id": "shirasagi-reina",
            "tool_call_id": "tool-2",
            "tool_name": "memory.search",
        }
    )

    send_async.assert_awaited_once()
    request = send_async.await_args.args[0]
    assert isinstance(request, HandleToolExecutionCommand)
    assert request.tool_call_id == "tool-2"
    assert request.tool_name == "memory.search"


@pytest.mark.anyio
async def test_chat_tool_completed_dispatches_agent_runtime(
    mocker: Any,
) -> None:
    """Test that tool completion re-enters the agent runtime."""

    send_async = cast(Any, AsyncMock(return_value=None))
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_completed(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "chat_type": "DISCORD",
            "character_id": "shirasagi-reina",
            "status": "ok",
            "tool_name": "web_search",
            "tool_call_id": "tool-1",
            "result": {
                "tool_call_id": "tool-1",
                "retrieved_context": True,
                "result_count": 1,
            },
        }
    )

    send_async.assert_awaited_once()
    request = send_async.await_args.args[0]
    assert isinstance(request, RunAgentTurnQuery)
    assert request.tool_call_id == "tool-1"


@pytest.mark.anyio
async def test_chat_tool_completed_non_search_tool_does_not_reenter(
    mocker: Any,
) -> None:
    """Test that send-only tools do not trigger another agent turn."""

    send_async = cast(Any, AsyncMock(return_value=None))
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_completed(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "chat_type": "DISCORD",
            "character_id": "shirasagi-reina",
            "status": "ok",
            "tool_name": "discord.reply",
            "result": {
                "content_count": 1,
            },
        }
    )

    send_async.assert_not_awaited()
