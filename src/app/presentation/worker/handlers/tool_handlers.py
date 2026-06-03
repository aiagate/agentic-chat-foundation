"""Worker handlers for generic tool events."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.chat_events import (
    CHAT_TOOL_COMPLETED_TOPIC,
    CHAT_TOOL_REQUESTED_TOPIC,
)
from app.presentation.worker.event_payloads import (
    ChatToolCompletedPayload,
    ChatToolRequestedPayload,
    extract_agent_envelope,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.handle_tool_execution import HandleToolExecutionCommand
from app.usecases.agent.run_agent_turn import RunAgentTurnQuery

logger = logging.getLogger(__name__)

_RETRIEVED_CONTEXT_TOOL_NAMES = {"web_search", "memory.search"}


def _require_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


@event_handler(CHAT_TOOL_REQUESTED_TOPIC)
async def on_chat_tool_requested(payload: Mapping[str, object]) -> None:
    """Execute a requested generic tool."""

    event = parse_worker_event_payload(
        ChatToolRequestedPayload,
        payload,
        event_name="Tool requested",
    )
    if event is None:
        return

    if event.tool_call_id is None:
        logger.warning("Tool requested payload missing tool_call_id: %s", payload)
        return

    await Mediator.send_async(
        HandleToolExecutionCommand(
            chat_id=event.chat_id,
            tool_call_id=event.tool_call_id,
            user_id=event.user_id,
            chat_type=event.chat_type,
            tool_name=event.tool_name,
            character_id=event.character_id,
            guild_id=event.guild_id,
            channel_id=event.channel_id,
            agent_context=extract_agent_envelope(event),
        )
    )


@event_handler(CHAT_TOOL_COMPLETED_TOPIC)
async def on_chat_tool_completed(payload: Mapping[str, object]) -> None:
    """Re-enter the agent runtime after a generic tool completes."""

    event = parse_worker_event_payload(
        ChatToolCompletedPayload,
        payload,
        event_name="Tool completed",
    )
    if event is None:
        return

    if event.status != "ok":
        if event.tool_name != "web_search":
            return
        await Mediator.send_async(
            RunAgentTurnQuery(
                chat_id=event.chat_id,
                source_request_id=event.chat_id,
                guild_id=event.guild_id or "LINE",
                channel_id=event.channel_id or event.chat_id,
                user_id=event.user_id or event.chat_id,
                chat_type=event.chat_type,
                character_id=event.character_id,
                tool_failure_context=_tool_failure_context(
                    tool_name=event.tool_name,
                    error=event.error,
                ),
                agent_context=extract_agent_envelope(event),
            )
        )
        return

    if event.tool_name not in _RETRIEVED_CONTEXT_TOOL_NAMES:
        return

    result = event.result
    if result is None:
        return

    has_retrieved_context = result.get("retrieved_context") is True
    tool_call_id = event.tool_call_id or _require_str(result, "tool_call_id")
    if not has_retrieved_context or not tool_call_id:
        return

    await Mediator.send_async(
        RunAgentTurnQuery(
            chat_id=event.chat_id,
            tool_call_id=tool_call_id,
            source_request_id=event.chat_id,
            guild_id=event.guild_id or "LINE",
            channel_id=event.channel_id or event.chat_id,
            user_id=event.user_id or event.chat_id,
            chat_type=event.chat_type,
            character_id=event.character_id,
            agent_context=extract_agent_envelope(event),
        )
    )


def _tool_failure_context(*, tool_name: str, error: str | None) -> str:
    rendered_error = error or "unknown error"
    return (
        f"Tool failure context: {tool_name} failed with error: {rendered_error}. "
        "Continue the reply without using that tool again unless absolutely necessary."
    )
