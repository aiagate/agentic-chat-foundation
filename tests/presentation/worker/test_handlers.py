"""Tests for worker event handlers."""

from datetime import time
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_med import Mediator

from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.handlers.chat_reply_handlers import (
    on_discord_chat_saved,
    on_line_chat_saved,
)
from app.presentation.worker.handlers.memory_sleep_handlers import (
    run_memory_sleep_scheduled_task,
)
from app.presentation.worker.handlers.search_handlers import (
    on_chat_search_completed,
    on_chat_search_requested,
)
from app.presentation.worker.handlers.user_handlers import on_user_created
from app.usecases.chat.generate_content import GenerateContentQuery
from app.usecases.chat.generate_content_with_retrieved_context import (
    GenerateContentWithRetrievedContextQuery,
)
from app.usecases.memory.run_memory_sleep import RunMemorySleepCommand
from app.usecases.search.handle_search_request import HandleSearchRequestCommand
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
            "content": "hello",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, GenerateContentQuery)
    assert request.chat_type is ChatType.DISCORD
    assert request.user_id == "u1"


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
            "content": "hello",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, GenerateContentQuery)
    assert request.chat_type is ChatType.LINE
    assert request.user_id == "u1"


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
async def test_chat_search_requested_handler_triggers_search(
    mocker: Any,
) -> None:
    """Test that search requests dispatch the search command."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_search_requested(
        {
            "search_session_id": "search-1",
            "source_request_id": "req-1",
            "chat_id": "chat-1",
            "user_id": "u1",
            "prompt": "prompt",
            "query": "query",
            "user_message": "message",
            "tool_name": "web_search",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, HandleSearchRequestCommand)
    assert request.search_session_id == "search-1"


@pytest.mark.anyio
async def test_chat_search_completed_handler_triggers_regeneration(
    mocker: Any,
) -> None:
    """Test that completed search dispatches regeneration."""

    send_async = AsyncMock(return_value=None)
    mocker.patch.object(Mediator, "send_async", send_async)

    await on_chat_search_completed(
        {
            "search_session_id": "search-1",
            "chat_id": "chat-1",
            "prompt": "prompt",
            "chat_type": "line",
        }
    )

    send_async.assert_awaited_once()
    request = cast(Any, send_async.await_args).args[0]
    assert isinstance(request, GenerateContentWithRetrievedContextQuery)
    assert request.search_session_id == "search-1"
