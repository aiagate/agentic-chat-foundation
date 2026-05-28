"""Discord reply sender helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

import discord

logger = logging.getLogger(__name__)


async def send_discord_reply(
    bot: Any,
    payload: Mapping[str, object],
) -> None:
    """Send a generated reply to a Discord channel."""
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str):
        logger.warning("Discord reply payload missing channel_id: %s", payload)
        return

    contents = payload.get("contents")
    content = payload.get("content")
    if not channel_id or (not content and not contents):
        logger.warning("Discord reply payload missing required fields: %s", payload)
        return

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except discord.DiscordException:
            logger.exception("Failed to fetch Discord channel %s", channel_id)
            return

    messageable = cast(discord.abc.Messageable, channel)
    if isinstance(contents, list) and contents:
        for item in contents:
            await messageable.send(str(item))
        return
    await messageable.send(str(content))
