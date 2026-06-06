"""Application error event payloads."""

from __future__ import annotations

from typing import NotRequired, Required, TypedDict, cast

APP_ERROR_DETECTED_TOPIC = "app.error.detected"


class AppErrorDetectedPayload(TypedDict, total=False):
    """Payload for observed application-level errors."""

    layer: Required[str]
    operation: Required[str]
    operation_type: Required[str]
    status: Required[str]
    error_type: Required[str]
    error_code: Required[str]
    message: Required[str]
    retryable: Required[bool]
    request_type: Required[str]
    chat_type: NotRequired[str]
    character_id: NotRequired[str]
    chat_id: NotRequired[str]
    user_id: NotRequired[str]
    guild_id: NotRequired[str]
    channel_id: NotRequired[str]
    source_request_id: NotRequired[str]
    tool_name: NotRequired[str]
    event_id: NotRequired[str]
    correlation_id: NotRequired[str]
    causation_id: NotRequired[str]
    agent_run_id: NotRequired[str]
    agent_turn_id: NotRequired[str]
    tool_call_id: NotRequired[str]
    source_message_id: NotRequired[str]
    decision_summary: NotRequired[str]


def build_app_error_detected_payload(
    *,
    layer: str,
    operation: str,
    operation_type: str,
    status: str,
    error_type: str,
    error_code: str,
    message: str,
    retryable: bool,
    request_type: str,
    chat_type: str | None = None,
    character_id: str | None = None,
    chat_id: str | None = None,
    user_id: str | None = None,
    guild_id: str | None = None,
    channel_id: str | None = None,
    source_request_id: str | None = None,
    tool_name: str | None = None,
    event_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    agent_run_id: str | None = None,
    agent_turn_id: str | None = None,
    tool_call_id: str | None = None,
    source_message_id: str | None = None,
    decision_summary: str | None = None,
) -> AppErrorDetectedPayload:
    """Build a payload for a detected application error."""

    payload: dict[str, object] = {
        "layer": layer,
        "operation": operation,
        "operation_type": operation_type,
        "status": status,
        "error_type": error_type,
        "error_code": error_code,
        "message": message,
        "retryable": retryable,
        "request_type": request_type,
    }
    if chat_type is not None:
        payload["chat_type"] = chat_type
    if character_id is not None:
        payload["character_id"] = character_id
    if chat_id is not None:
        payload["chat_id"] = chat_id
    if user_id is not None:
        payload["user_id"] = user_id
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    if source_request_id is not None:
        payload["source_request_id"] = source_request_id
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if event_id is not None:
        payload["event_id"] = event_id
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    if causation_id is not None:
        payload["causation_id"] = causation_id
    if agent_run_id is not None:
        payload["agent_run_id"] = agent_run_id
    if agent_turn_id is not None:
        payload["agent_turn_id"] = agent_turn_id
    if tool_call_id is not None:
        payload["tool_call_id"] = tool_call_id
    if source_message_id is not None:
        payload["source_message_id"] = source_message_id
    if decision_summary is not None:
        payload["decision_summary"] = decision_summary
    return cast(AppErrorDetectedPayload, payload)
