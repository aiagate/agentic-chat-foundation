"""Discord delivery adapter for autonomous discussion turns."""

from __future__ import annotations

import discord

from app.contracts.messages.discussion import SentDiscussionMessage
from app.contracts.ports.discussion import IDiscussionMessageSender

_DISCORD_TEXT_LIMIT = 2000


class DiscordDiscussionMessageSender(IDiscussionMessageSender):
    """Send every selected text through the current bot account."""

    def __init__(self, channel: discord.abc.Messageable) -> None:
        self._channel = channel

    async def send(self, texts: list[str]) -> list[SentDiscussionMessage]:
        sent_messages: list[SentDiscussionMessage] = []
        for text in texts:
            for chunk in _chunks(text):
                sent = await self._channel.send(chunk)
                sent_messages.append(
                    SentDiscussionMessage(
                        external_message_id=str(sent.id),
                        text=sent.content,
                        occurred_at=sent.created_at,
                    )
                )
        if not sent_messages:
            raise ValueError("Discussion sender received no public text")
        return sent_messages


def _chunks(text: str) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    return [
        normalized[index : index + _DISCORD_TEXT_LIMIT]
        for index in range(0, len(normalized), _DISCORD_TEXT_LIMIT)
    ]
