"""Worker handlers for saved chat events."""

import logging
from typing import Any

from flow_med import Mediator

from app.contracts.messages.chat_events import (
    DISCORD_CHAT_SAVED_TOPIC,
    LINE_CHAT_SAVED_TOPIC,
)
from app.domain.value_objects.chat_type import ChatType
from app.presentation.worker.registry import event_handler
from app.usecases.chat.generate_content import GenerateContentQuery

logger = logging.getLogger(__name__)


@event_handler(DISCORD_CHAT_SAVED_TOPIC)
async def on_discord_chat_saved(payload: dict[str, Any]) -> None:
    """Handle a saved Discord chat message."""

    chat_id = payload.get("chat_id")
    content = payload.get("content")
    if not chat_id or not content:
        logger.warning("Chat saved payload missing required fields: %s", payload)
        return

    guild_id = payload.get("guild_id")
    channel_id = payload.get("channel_id")
    if not guild_id or not channel_id:
        logger.warning("Discord chat payload missing route fields: %s", payload)
        return

    await Mediator.send_async(
        GenerateContentQuery(
            prompt=content,
            chat_id=str(chat_id),
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=str(payload.get("user_id") or chat_id),
            chat_type=ChatType.DISCORD,
        )
    )


@event_handler(LINE_CHAT_SAVED_TOPIC)
async def on_line_chat_saved(payload: dict[str, Any]) -> None:
    """Handle a saved LINE chat message."""

    chat_id = payload.get("chat_id")
    content = payload.get("content")
    if not chat_id or not content:
        logger.warning("Chat saved payload missing required fields: %s", payload)
        return

    user_id = payload.get("user_id")
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
