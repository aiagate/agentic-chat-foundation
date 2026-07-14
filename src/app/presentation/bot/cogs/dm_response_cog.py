"""Cog to handle automated responses to direct messages."""

import logging
from typing import Any, cast

import discord
from discord.ext import commands
from flow_med import Mediator
from flow_res import is_err

from app.contracts.messages.conversation import IncomingMessage
from app.presentation.bot.cogs.base_cog import BaseCog
from app.presentation.bot.discord_conversation_sender import (
    DiscordConversationResultSender,
)
from app.presentation.conversation_flow import ConversationFlow
from app.usecases.conversation.accept_incoming_message import (
    AcceptIncomingMessageCommand,
)

logger = logging.getLogger(__name__)


class DirectMessageResponseCog(BaseCog, name="DM Response"):
    """Cog to handle automated responses to direct messages."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listen for messages and respond to DMs directly."""
        if message.author == self.bot.user:
            return

        if not isinstance(message.channel, discord.DMChannel):
            return

        content = _normalize_message_content(message.content)
        if content is None:
            logger.warning(
                "Skipping Discord DM without text content: author_id=%s channel_id=%s",
                getattr(message.author, "id", None),
                getattr(message.channel, "id", None),
            )
            return

        guild_id = "DM"
        channel_id = str(message.channel.id)

        incoming = IncomingMessage(
            channel="discord",
            external_conversation_id=channel_id,
            external_participant_id=str(message.author.id),
            text=content,
            external_message_id=str(getattr(message, "id", "")),
            metadata={"guild_id": guild_id, "channel_id": channel_id},
        )
        if not hasattr(self.bot, "injector"):
            await Mediator.send_async(AcceptIncomingMessageCommand(incoming))
            return
        injector = cast(Any, self.bot).injector
        result = await injector.get(ConversationFlow).process(
            incoming,
            DiscordConversationResultSender(message.channel),
        )
        if is_err(result):
            await message.channel.send("メッセージの処理に失敗しました。")
            return


def _normalize_message_content(content: str | None) -> str | None:
    if content is None:
        return None
    normalized = content.strip()
    if not normalized:
        return None
    return normalized
