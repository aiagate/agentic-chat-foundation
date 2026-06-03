"""Validated DTOs for worker event payloads."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from app.contracts.messages.agentic import AgentEnvelope
from app.domain.value_objects.chat_type import ChatType

logger = logging.getLogger(__name__)

_AGENT_ENVELOPE_FIELDS = {
    "event_id",
    "correlation_id",
    "causation_id",
    "agent_run_id",
    "agent_turn_id",
    "character_id",
    "tool_call_id",
    "source_message_id",
    "decision_summary",
}


def parse_worker_event_payload[TEventPayload: BaseModel](
    model: type[TEventPayload],
    payload: Mapping[str, object],
    *,
    event_name: str,
) -> TEventPayload | None:
    """Validate an inbound worker payload and log a concise warning on failure."""

    try:
        return model.model_validate(payload)
    except ValidationError:
        logger.warning("%s payload missing required fields: %s", event_name, payload)
        return None


def extract_agent_envelope(payload: AgentEnvelope) -> AgentEnvelope | None:
    """Return the shared agent metadata embedded in a payload, if any."""

    envelope_data = payload.model_dump(
        exclude_none=True,
        include=_AGENT_ENVELOPE_FIELDS,
    )
    if not envelope_data:
        return None
    return AgentEnvelope.model_validate(envelope_data)


class DiscordChatSavedPayload(AgentEnvelope):
    """Validated payload for `chat.discord.saved`."""

    chat_id: str
    user_id: str
    guild_id: str
    channel_id: str


class LineChatSavedPayload(AgentEnvelope):
    """Validated payload for `chat.line.saved`."""

    chat_id: str
    user_id: str


class ChatToolRequestedPayload(AgentEnvelope):
    """Validated payload for `chat.tool.requested`."""

    chat_id: str
    user_id: str
    chat_type: ChatType
    tool_name: str
    guild_id: str | None = None
    channel_id: str | None = None


class ChatToolCompletedPayload(AgentEnvelope):
    """Validated payload for `chat.tool.completed`."""

    chat_id: str
    chat_type: ChatType
    user_id: str | None
    status: str
    tool_name: str
    result: dict[str, object] | None = None
    error: str | None = None
    error_code: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None


class AppErrorDetectedPayload(AgentEnvelope):
    """Validated payload for `app.error.detected`."""

    layer: str | None = None
    operation: str
    operation_type: str | None = None
    status: str | None = None
    error_type: str | None = None
    error_code: str
    message: str
    retryable: bool | None = None
    request_type: str | None = None
    chat_type: ChatType | None = None
    chat_id: str | None = None
    user_id: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    source_request_id: str | None = None
    tool_name: str | None = None


class UserCreatedPayload(AgentEnvelope):
    """Validated payload for `user.created`."""

    user_id: str
