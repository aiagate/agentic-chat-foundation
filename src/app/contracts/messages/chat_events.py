"""Chat event topics and payload builders."""

from __future__ import annotations

from typing import NotRequired, Required, TypedDict, cast

from app.contracts.messages.agentic import AgentEnvelope
from app.domain.value_objects.chat_type import ChatType

CHAT_TOOL_REQUESTED_TOPIC = "chat.tool.requested"
CHAT_TOOL_COMPLETED_TOPIC = "chat.tool.completed"
DISCORD_CHAT_SAVED_TOPIC = "chat.discord.saved"
LINE_CHAT_SAVED_TOPIC = "chat.line.saved"
DISCORD_CHAT_REPLY_READY_TOPIC = "chat.discord.reply_ready"
LINE_CHAT_REPLY_READY_TOPIC = "chat.line.reply_ready"

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


class AgentEventPayload(TypedDict, total=False):
    """Optional agentic metadata attached to chat events."""

    event_id: str
    correlation_id: str
    causation_id: str
    agent_run_id: str
    agent_turn_id: str
    character_id: str
    tool_call_id: str
    source_message_id: str
    decision_summary: str


class ChatToolRequestedPayload(AgentEventPayload):
    """Payload for a generic tool request event."""

    chat_id: Required[str]
    user_id: Required[str]
    chat_type: Required[str]
    tool_name: Required[str]
    guild_id: NotRequired[str]
    channel_id: NotRequired[str]


class ChatToolCompletedPayload(AgentEventPayload):
    """Payload for a generic tool completion event."""

    chat_id: Required[str]
    chat_type: Required[str]
    user_id: Required[str | None]
    status: Required[str]
    tool_name: Required[str]
    result: NotRequired[dict[str, object]]
    error: NotRequired[str]
    error_code: NotRequired[str]
    guild_id: NotRequired[str]
    channel_id: NotRequired[str]


class DiscordChatSavedPayload(AgentEventPayload):
    """Payload for a saved Discord chat event."""

    chat_id: Required[str]
    user_id: Required[str]
    guild_id: Required[str]
    channel_id: Required[str]


class LineChatSavedPayload(AgentEventPayload):
    """Payload for a saved LINE chat event."""

    chat_id: Required[str]
    user_id: Required[str]


class ReplyReadyPayload(AgentEventPayload):
    """Payload for a generated reply event."""

    chat_type: Required[str]
    contents: Required[list[str]]
    guild_id: NotRequired[str]
    channel_id: NotRequired[str]
    user_id: NotRequired[str]


def _apply_agent_envelope(
    payload: dict[str, object],
    agent_envelope: AgentEnvelope | None,
) -> None:
    """Merge optional agent metadata into a payload."""

    if agent_envelope is None:
        return
    payload.update(
        agent_envelope.model_dump(
            exclude_none=True,
            include=_AGENT_ENVELOPE_FIELDS,
        )
    )


def build_discord_chat_saved_payload(
    *,
    chat_id: str,
    user_id: str,
    guild_id: str,
    channel_id: str,
    agent_envelope: AgentEnvelope | None = None,
) -> DiscordChatSavedPayload:
    """Build a payload for a saved Discord chat event."""
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "guild_id": guild_id,
        "channel_id": channel_id,
    }
    _apply_agent_envelope(payload, agent_envelope)
    return cast(DiscordChatSavedPayload, payload)


def build_chat_tool_requested_payload(
    *,
    chat_id: str,
    user_id: str,
    chat_type: str,
    tool_call_id: str,
    tool_name: str,
    guild_id: str | None = None,
    channel_id: str | None = None,
    agent_envelope: AgentEnvelope | None = None,
) -> ChatToolRequestedPayload:
    """Build a payload for a generic tool request event."""
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "chat_type": chat_type,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
    }
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    _apply_agent_envelope(payload, agent_envelope)
    return cast(ChatToolRequestedPayload, payload)


def build_chat_tool_completed_payload(
    *,
    chat_id: str,
    chat_type: str,
    user_id: str | None,
    status: str,
    tool_name: str,
    result: dict[str, object] | None = None,
    error: str | None = None,
    error_code: str | None = None,
    guild_id: str | None = None,
    channel_id: str | None = None,
    agent_envelope: AgentEnvelope | None = None,
) -> ChatToolCompletedPayload:
    """Build a payload for a generic tool completion event."""
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "user_id": user_id,
        "status": status,
        "tool_name": tool_name,
    }
    if result is not None:
        payload["result"] = result
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    if error is not None:
        payload["error"] = error
    if error_code is not None:
        payload["error_code"] = error_code
    _apply_agent_envelope(payload, agent_envelope)
    return cast(ChatToolCompletedPayload, payload)


def build_line_chat_saved_payload(
    *,
    chat_id: str,
    user_id: str,
    agent_envelope: AgentEnvelope | None = None,
) -> LineChatSavedPayload:
    """Build a payload for a saved LINE chat event."""
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "user_id": user_id,
    }
    _apply_agent_envelope(payload, agent_envelope)
    return cast(LineChatSavedPayload, payload)


def build_reply_ready_payload(
    *,
    chat_type: ChatType,
    contents: list[str],
    guild_id: str | None = None,
    channel_id: str | None = None,
    user_id: str | None = None,
    agent_envelope: AgentEnvelope | None = None,
) -> ReplyReadyPayload:
    """Build a payload for a generated reply event."""
    payload: dict[str, object] = {
        "chat_type": chat_type.to_primitive(),
        "contents": contents,
    }
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    if user_id is not None:
        payload["user_id"] = user_id
    _apply_agent_envelope(payload, agent_envelope)
    return cast(ReplyReadyPayload, payload)


def reply_topic_for(chat_type: ChatType) -> str:
    """Return the reply-ready topic for a given chat type."""
    match chat_type:
        case ChatType.DISCORD:
            return DISCORD_CHAT_REPLY_READY_TOPIC
        case ChatType.LINE:
            return LINE_CHAT_REPLY_READY_TOPIC
    raise ValueError(f"Unsupported chat type: {chat_type}")
