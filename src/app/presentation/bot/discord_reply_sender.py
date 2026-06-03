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

    contents = _normalize_contents(payload)
    if not channel_id or not contents:
        logger.warning("Discord reply payload missing required fields: %s", payload)
        return

    logger.info("Sending Discord reply to channel %s", channel_id)

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except discord.DiscordException:
            logger.exception("Failed to fetch Discord channel %s", channel_id)
            return

    messageable = cast(discord.abc.Messageable, channel)
    for item in contents:
        await messageable.send(item)
    logger.info(
        "Discord reply sent to channel %s (%d messages)", channel_id, len(contents)
    )


def _normalize_contents(payload: Mapping[str, object]) -> list[str]:
    contents = payload.get("contents")
    if isinstance(contents, list):
        normalized = [
            str(content).strip() for content in contents if str(content).strip()
        ]
        if normalized:
            return normalized

    return []
