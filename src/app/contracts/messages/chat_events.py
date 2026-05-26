"""Chat event topics and payload builders."""

from __future__ import annotations

from typing import Any

from app.domain.value_objects.chat_type import ChatType

DISCORD_CHAT_SAVED_TOPIC = "chat.discord.saved"
LINE_CHAT_SAVED_TOPIC = "chat.line.saved"
DISCORD_CHAT_REPLY_READY_TOPIC = "chat.discord.reply_ready"
LINE_CHAT_REPLY_READY_TOPIC = "chat.line.reply_ready"
CHAT_SEARCH_REQUESTED_TOPIC = "chat.search.requested"
CHAT_SEARCH_COMPLETED_TOPIC = "chat.search.completed"


def build_discord_chat_saved_payload(
    *,
    chat_id: str,
    user_id: str,
    guild_id: str,
    channel_id: str,
    content: str,
) -> dict[str, Any]:
    """Build a payload for a saved Discord chat event."""
    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "content": content,
    }


def build_line_chat_saved_payload(
    *,
    chat_id: str,
    user_id: str,
    content: str,
) -> dict[str, Any]:
    """Build a payload for a saved LINE chat event."""
    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "content": content,
    }


def build_reply_ready_payload(
    *,
    chat_type: ChatType,
    contents: list[str],
    guild_id: str | None = None,
    channel_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Build a payload for a generated reply event."""
    content = "\n".join(content for content in contents if content)
    payload: dict[str, Any] = {
        "chat_type": chat_type.to_primitive(),
        "content": content,
    }
    payload["contents"] = contents
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    if user_id is not None:
        payload["user_id"] = user_id
    return payload


def build_chat_search_requested_payload(
    *,
    search_session_id: str,
    source_request_id: str,
    chat_id: str,
    user_id: str,
    chat_type: str,
    prompt: str,
    query: str,
    tool_name: str,
    user_message: str,
    max_results: int | None = None,
    guild_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Build a payload for a requested search event."""
    payload: dict[str, Any] = {
        "search_session_id": search_session_id,
        "source_request_id": source_request_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "chat_type": chat_type,
        "prompt": prompt,
        "query": query,
        "tool_name": tool_name,
        "user_message": user_message,
    }
    if max_results is not None:
        payload["max_results"] = max_results
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    return payload


def build_chat_search_completed_payload(
    *,
    search_session_id: str,
    source_request_id: str,
    chat_id: str,
    chat_type: str,
    user_id: str | None,
    prompt: str,
    status: str,
    result_count: int,
    tool_name: str,
    error: str | None = None,
    guild_id: str | None = None,
    channel_id: str | None = None,
) -> dict[str, Any]:
    """Build a payload for a completed search event."""
    payload: dict[str, Any] = {
        "search_session_id": search_session_id,
        "source_request_id": source_request_id,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "user_id": user_id,
        "prompt": prompt,
        "status": status,
        "result_count": result_count,
        "tool_name": tool_name,
    }
    if guild_id is not None:
        payload["guild_id"] = guild_id
    if channel_id is not None:
        payload["channel_id"] = channel_id
    if error is not None:
        payload["error"] = error
    return payload


def reply_topic_for(chat_type: ChatType) -> str:
    """Return the reply-ready topic for a given chat type."""
    match chat_type:
        case ChatType.DISCORD:
            return DISCORD_CHAT_REPLY_READY_TOPIC
        case ChatType.LINE:
            return LINE_CHAT_REPLY_READY_TOPIC
    raise ValueError(f"Unsupported chat type: {chat_type}")
