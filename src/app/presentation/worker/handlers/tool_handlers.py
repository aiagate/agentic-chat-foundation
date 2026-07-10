"""Worker handler for durable AgentToolCall requests."""

from __future__ import annotations

from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.agent_run_events import AGENT_TOOL_REQUESTED_TOPIC
from app.presentation.worker.event_payloads import (
    AgentToolRequestedPayload,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.execute_agent_tool import ExecuteAgentToolCommand


@event_handler(AGENT_TOOL_REQUESTED_TOPIC)
async def on_agent_tool_requested(payload: Mapping[str, object]) -> None:
    """Execute a durable tool request."""
    event = parse_worker_event_payload(
        AgentToolRequestedPayload,
        payload,
        event_name="Agent tool requested",
    )
    if event is None:
        return
    await Mediator.send_async(
        ExecuteAgentToolCommand(
            agent_run_id=event.agent_run_id,
            tool_call_id=event.tool_call_id,
            attempt_count=event.attempt_count,
        )
    )
