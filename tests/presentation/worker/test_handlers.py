"""Tests for worker event handlers."""

from datetime import time
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_med import Mediator

from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.handlers.app_error_handlers import on_app_error_detected
from app.presentation.worker.handlers.chat_reply_handlers import (
    on_discord_chat_saved,
    on_line_chat_saved,
)
from app.presentation.worker.handlers.memory_sleep_handlers import (
    run_memory_sleep_scheduled_task,
)
from app.presentation.worker.handlers.tool_handlers import (
    on_chat_tool_completed,
    on_chat_tool_requested,
)
from app.presentation.worker.handlers.user_handlers import on_user_created
from app.usecases.agent.handle_tool_execution import HandleToolExecutionCommand
from app.usecases.agent.run_agent_turn import RunAgentTurnQuery
from app.usecases.memory.run_memory_sleep import RunMemorySleepCommand
from app.usecases.users.welcome_user import WelcomeUserCommand


@pytest.mark.anyio
async def test_discord_chat_saved_handler_triggers_generation(
    mocker: Any,
) -> None:
    """Test that Discord saved events trigger content generation."""
    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_discord_chat_saved(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "guild_id": "DM",
            "channel_id": "123",
            "event_id": "event-1",
            "agent_run_id": "run-1",
            "tool_call_id": "tool-1",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, RunAgentTurnQuery)
    assert request.chat_type is ChatType.DISCORD
    assert request.user_id == "u1"
    assert request.agent_context is not None
    assert request.agent_context.agent_run_id == "run-1"


@pytest.mark.anyio
async def test_line_chat_saved_handler_triggers_generation(
    mocker: Any,
) -> None:
    """Test that LINE saved events trigger content generation."""
    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_line_chat_saved(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "event_id": "event-2",
            "agent_run_id": "run-2",
            "tool_call_id": "tool-2",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, RunAgentTurnQuery)
    assert request.chat_type is ChatType.LINE
    assert request.user_id == "u1"
    assert request.agent_context is not None
    assert request.agent_context.agent_run_id == "run-2"


@pytest.mark.anyio
async def test_memory_sleep_scheduled_task_triggers_command(
    mocker: Any,
) -> None:
    """Test that the periodic task dispatches the sleep command."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await run_memory_sleep_scheduled_task()

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, RunMemorySleepCommand)


def test_memory_sleep_scheduled_task_runs_at_three_am() -> None:
    """Test that the sleep task is aligned to 03:00."""

    scheduled_task = cast(Any, run_memory_sleep_scheduled_task)
    assert scheduled_task.schedule_run_time == time(hour=3)


@pytest.mark.anyio
async def test_user_created_handler_triggers_welcome(
    mocker: Any,
) -> None:
    """Test that user.created dispatches the welcome command."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_user_created({"user_id": "u1"})

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, WelcomeUserCommand)
    assert request.user_id == "u1"


@pytest.mark.anyio
async def test_chat_tool_completed_error_for_web_search_keeps_reprompting(
    mocker: Any,
) -> None:
    """Test that failed web_search tool completions still re-enter the agent loop."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_completed(
        {
            "chat_id": "chat-1",
            "chat_type": "DISCORD",
            "status": "error",
            "user_id": "u1",
            "guild_id": "DM",
            "channel_id": "123",
            "tool_name": "web_search",
            "error": "HTTP 500",
            "event_id": "event-5",
            "agent_run_id": "run-5",
            "tool_call_id": "tool-5",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, RunAgentTurnQuery)
    assert request.tool_failure_context is not None
    assert "HTTP 500" in request.tool_failure_context


@pytest.mark.anyio
async def test_chat_tool_requested_handler_triggers_execution(
    mocker: Any,
) -> None:
    """Test that generic tool requests dispatch the execution command."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_requested(
        {
            "chat_id": "chat-1",
            "user_id": "u1",
            "chat_type": "DISCORD",
            "tool_call_id": "tool-6",
            "tool_name": "web_search",
            "event_id": "event-6",
            "agent_run_id": "run-6",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, HandleToolExecutionCommand)
    assert request.tool_call_id == "tool-6"
    assert request.tool_name == "web_search"


@pytest.mark.anyio
async def test_chat_tool_completed_error_status_is_ignored_for_non_search_tools(
    mocker: Any,
) -> None:
    """Test that non-search tool completion errors do not re-enter the agent loop."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_tool_completed(
        {
            "chat_id": "chat-1",
            "chat_type": "DISCORD",
            "status": "error",
            "user_id": "u1",
            "guild_id": "DM",
            "channel_id": "123",
            "tool_name": "memory.search",
            "event_id": "event-5",
            "agent_run_id": "run-5",
            "tool_call_id": "tool-5",
        }
    )

    send_async.assert_not_awaited()


@pytest.mark.anyio
async def test_app_error_detected_handler_triggers_agent_reentry(
    mocker: Any,
) -> None:
    """Test that observed use case errors can re-enter the agent loop."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_app_error_detected(
        {
            "operation": "RunWebSearchCommand",
            "error_code": "unexpected",
            "message": "Search failed",
            "chat_id": "chat-1",
            "chat_type": "DISCORD",
            "user_id": "u1",
            "guild_id": "DM",
            "channel_id": "123",
            "source_request_id": "req-1",
            "event_id": "event-7",
            "agent_run_id": "run-7",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, RunAgentTurnQuery)
    assert request.source_request_id == "req-1"
    assert request.agent_context is not None
    assert request.agent_context.agent_run_id == "run-7"
    assert request.tool_failure_context is not None
    assert "RunWebSearchCommand failed with unexpected" in (
        request.tool_failure_context
    )


@pytest.mark.anyio
async def test_app_error_detected_handler_skips_inference_errors(
    mocker: Any,
) -> None:
    """Test that inference use case errors do not recursively re-enter inference."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_app_error_detected(
        {
            "operation": "RunAgentTurnQuery",
            "error_code": "unexpected",
            "message": "LLM failed",
            "chat_id": "chat-1",
            "chat_type": "DISCORD",
            "user_id": "u1",
        }
    )

    send_async.assert_not_awaited()


@pytest.mark.anyio
async def test_app_error_detected_handler_requires_route_fields(
    mocker: Any,
) -> None:
    """Test that unroutable errors are observed but not sent to the agent."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_app_error_detected(
        {
            "operation": "RunWebSearchCommand",
            "error_code": "unexpected",
            "message": "Search failed",
        }
    )

    send_async.assert_not_awaited()
