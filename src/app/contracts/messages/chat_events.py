"""Chat event topics and payload builders."""

from __future__ import annotations

from typing import NotRequired, Required, TypedDict, cast

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_type import ChatType

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
