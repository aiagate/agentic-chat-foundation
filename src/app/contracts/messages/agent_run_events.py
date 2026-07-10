"""Durable AgentRun event topics and payload builders."""

from __future__ import annotations

from typing import Required, TypedDict

AGENT_RUN_WAKEUP_TOPIC = "agent.run.wakeup"
AGENT_TOOL_REQUESTED_TOPIC = "agent.tool.requested"


class AgentRunWakeupPayload(TypedDict):
    """Request to advance one persisted AgentRun state machine."""

    agent_run_id: Required[str]
    wake_sequence: Required[int]


class AgentToolRequestedPayload(TypedDict):
    """Request to execute one persisted AgentToolCall."""

    agent_run_id: Required[str]
    tool_call_id: Required[str]
    attempt_count: Required[int]


def build_agent_run_wakeup_payload(
    *,
    agent_run_id: str,
    wake_sequence: int,
) -> AgentRunWakeupPayload:
    return AgentRunWakeupPayload(
        agent_run_id=agent_run_id,
        wake_sequence=wake_sequence,
    )


def build_agent_tool_requested_payload(
    *,
    agent_run_id: str,
    tool_call_id: str,
    attempt_count: int,
) -> AgentToolRequestedPayload:
    return AgentToolRequestedPayload(
        agent_run_id=agent_run_id,
        tool_call_id=tool_call_id,
        attempt_count=attempt_count,
    )


def wake_event_id(agent_run_id: str, wake_sequence: int) -> str:
    """Return a deterministic outbox id that fits the UUID-sized column."""

    return f"{agent_run_id}:w:{wake_sequence}"


def tool_request_event_id(tool_call_id: str, attempt_count: int) -> str:
    """Return a deterministic outbox id for one tool execution attempt."""

    return f"{tool_call_id[:28]}:t:{attempt_count}"
