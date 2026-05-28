"""Worker handlers for saved chat events."""

import logging
from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.chat_events import (
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
)
from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.registry import event_handler
from app.usecases.chat.generate_content import GenerateContentQuery

logger = logging.getLogger(__name__)


def _require_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


@event_handler(DISCORD_CHAT_SAVED_TOPIC)
async def on_discord_chat_saved(payload: Mapping[str, object]) -> None:
    """Handle a saved Discord chat message."""

    chat_id = _require_str(payload, "chat_id")
    content = _require_str(payload, "content")
    if not chat_id or not content:
        logger.warning("Chat saved payload missing required fields: %s", payload)
        return

    guild_id = _require_str(payload, "guild_id")
    channel_id = _require_str(payload, "channel_id")
    if not guild_id or not channel_id:
        logger.warning("Discord chat payload missing route fields: %s", payload)
        return

    await Mediator.send_async(
        GenerateContentQuery(
            prompt=content,
            chat_id=str(chat_id),
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=_require_str(payload, "user_id") or chat_id,
            chat_type=ChatType.DISCORD,
        )
    )


@event_handler(LINE_CHAT_SAVED_TOPIC)
async def on_line_chat_saved(payload: Mapping[str, object]) -> None:
    """Handle a saved LINE chat message."""

    chat_id = _require_str(payload, "chat_id")
    content = _require_str(payload, "content")
    if not chat_id or not content:
        logger.warning("Chat saved payload missing required fields: %s", payload)
        return

    user_id = _require_str(payload, "user_id")
    if not user_id:
        logger.warning("LINE chat payload missing user_id: %s", payload)
        return

    await Mediator.send_async(
        GenerateContentQuery(
            prompt=content,
            chat_id=str(chat_id),
            guild_id="LINE",
            channel_id=str(chat_id),
            user_id=user_id,
            chat_type=ChatType.LINE,
        )
    )
