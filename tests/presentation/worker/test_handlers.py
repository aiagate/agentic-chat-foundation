"""Tests for worker event handlers."""

from datetime import time
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_med import Mediator

from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.handlers import (
    on_discord_chat_saved,
    on_line_chat_saved,
    run_memory_sleep_scheduled_task,
)
from app.usecases.chat.generate_content import GenerateContentQuery
from app.usecases.memory.run_memory_sleep import RunMemorySleepCommand


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
