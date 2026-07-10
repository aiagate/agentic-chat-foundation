"""Worker adapters map durable transport messages to one use-case command."""

from unittest.mock import AsyncMock, patch

import pytest

from app.presentation.worker.handlers.agent_turn_handlers import on_agent_run_wakeup
from app.presentation.worker.handlers.tool_handlers import on_agent_tool_requested
from app.usecases.agent.advance_agent_run import AdvanceAgentRunCommand
from app.usecases.agent.execute_agent_tool import ExecuteAgentToolCommand


@pytest.mark.asyncio
async def test_wakeup_handler_dispatches_advance_command() -> None:
    with patch(
        "app.presentation.worker.handlers.agent_turn_handlers.Mediator.send_async",
        new=AsyncMock(),
    ) as send:
        await on_agent_run_wakeup({"agent_run_id": "run", "wake_sequence": 3})
    command = send.await_args_list[0].args[0]
    assert isinstance(command, AdvanceAgentRunCommand)
    assert command.wake_sequence == 3


@pytest.mark.asyncio
async def test_tool_handler_dispatches_durable_tool_command() -> None:
    with patch(
        "app.presentation.worker.handlers.tool_handlers.Mediator.send_async",
        new=AsyncMock(),
    ) as send:
        await on_agent_tool_requested(
            {"agent_run_id": "run", "tool_call_id": "tool", "attempt_count": 1}
        )
    command = send.await_args_list[0].args[0]
    assert isinstance(command, ExecuteAgentToolCommand)
    assert command.tool_call_id == "tool"
