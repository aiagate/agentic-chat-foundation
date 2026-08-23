"""Discord delivery adapter for one request-local conversation flow."""

from __future__ import annotations

import discord

from app.contracts.messages.conversation import ConversationResult, DeliveryResult
from app.contracts.ports.conversation import ConversationResultSender


class DiscordConversationResultSender(ConversationResultSender):
    """Send generated text directly to the originating Discord channel."""

    def __init__(self, channel: discord.abc.Messageable) -> None:
        self._channel = channel

    async def send(self, result: ConversationResult) -> DeliveryResult:
        contents = list(result.contents)
        if not contents and result.unavailable:
            contents = [result.failure_reason or "応答を作成できませんでした。"]
        if not contents:
            return DeliveryResult(
                message_id=result.message_id,
                delivered=False,
                failure_reason="Response has no text content",
            )
        delivered_count = 0
        try:
            for content in contents:
                await self._channel.send(content)
                delivered_count += 1
        except discord.DiscordException as exc:
            return DeliveryResult(
                message_id=result.message_id,
                delivered=False,
                delivered_count=delivered_count,
                failed_content_index=delivered_count,
                failure_reason=str(exc),
            )
        return DeliveryResult(
            message_id=result.message_id,
            delivered=True,
            delivered_count=delivered_count,
        )
