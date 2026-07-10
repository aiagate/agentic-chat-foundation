"""Worker handlers for observed application error events."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.app_error import APP_ERROR_DETECTED_TOPIC
from app.presentation.worker.event_payloads import (
    AppErrorDetectedPayload,
    extract_agent_envelope,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.agent.request_agent_turn import RequestAgentTurnCommand

logger = logging.getLogger(__name__)

_INFERENCE_OPERATIONS = {
    "HandleToolExecutionCommand",
    "RequestAgentTurnCommand",
    "RunAgentTurnCommand",
}


@event_handler(APP_ERROR_DETECTED_TOPIC)
async def on_app_error_detected(payload: Mapping[str, object]) -> None:
    """Re-enter the agent runtime after a non-inference use case error."""

    event = parse_worker_event_payload(
        AppErrorDetectedPayload,
        payload,
        event_name="App error detected",
    )
    if event is None:
        return

    operation = event.operation
    if operation in _INFERENCE_OPERATIONS:
        logger.info(
            "Skipping agent re-entry for inference operation error: operation=%s",
            operation,
        )
        return

    chat_type = event.chat_type
    chat_id = event.chat_id
    user_id = event.user_id or chat_id
    character_id = event.character_id
    if chat_type is None or chat_id is None or user_id is None or character_id is None:
        logger.warning("App error payload missing agent route fields: %s", payload)
        return

    guild_id = event.guild_id or "LINE"
    channel_id = event.channel_id or chat_id

    logger.info(
        "Re-entering agent turn after app error: operation=%s chat_id=%s chat_type=%s",
        operation,
        chat_id,
        chat_type.to_primitive(),
    )
    await Mediator.send_async(
        RequestAgentTurnCommand(
            chat_id=chat_id,
            source_request_id=event.source_request_id or chat_id,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            chat_type=chat_type,
            character_id=character_id,
            tool_failure_context=_tool_failure_context(event),
            agent_context=extract_agent_envelope(event),
        )
    )


def _tool_failure_context(payload: AppErrorDetectedPayload) -> str:
    operation = payload.operation or "unknown operation"
    error_code = payload.error_code or "unknown_error"
    message = payload.message or "unknown error"
    return (
        "Application error context: "
        f"{operation} failed with {error_code}: {message}. "
        "Explain the available next step briefly."
    )
