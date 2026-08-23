"""Observe configured Discord channels as an autonomous discussion bot."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, cast

import discord
from discord.ext import commands
from flow_res import is_err

from app.contracts.messages.discussion import (
    DiscussionAuthorKind,
    IncomingDiscussionMessage,
)
from app.presentation.bot.cogs.base_cog import BaseCog
from app.presentation.bot.discord_discussion_sender import (
    DiscordDiscussionMessageSender,
)
from app.usecases.discussion.process_discussion_message import (
    ProcessDiscussionMessageCommand,
    ProcessDiscussionMessageHandler,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscussionCogSettings:
    """Runtime identity and channel scope for one independent bot."""

    channel_ids: frozenset[int]
    character_id: str
    backfill_limit: int = 50
    response_delay_min_seconds: float = 2.0
    response_delay_max_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.response_delay_min_seconds < 0:
            raise ValueError("minimum response delay must not be negative")
        if self.response_delay_max_seconds < self.response_delay_min_seconds:
            raise ValueError("maximum response delay must be at least the minimum")


@dataclass(frozen=True, slots=True)
class _QueuedMessage:
    message: IncomingDiscussionMessage
    channel: discord.abc.Messageable


class DiscordDiscussionCog(BaseCog, name="Discord Discussion"):
    """Evaluate public messages while allowing pending turns to be superseded."""

    def __init__(self, bot: commands.Bot, settings: DiscussionCogSettings) -> None:
        super().__init__(bot)
        self._settings = settings
        self._tasks: set[asyncio.Task[None]] = set()
        self._backfilled = False

    async def cog_unload(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._backfilled:
            return
        self._backfilled = True
        for channel_id in self._settings.channel_ids:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except discord.DiscordException:
                    logger.exception(
                        "Failed to fetch discussion channel: channel_id=%s",
                        channel_id,
                    )
                    continue
            if not isinstance(channel, discord.TextChannel | discord.Thread):
                logger.warning(
                    "Configured discussion channel cannot provide history: channel_id=%s",
                    channel_id,
                )
                continue
            try:
                messages = [
                    item
                    async for item in channel.history(
                        limit=self._settings.backfill_limit,
                        oldest_first=True,
                    )
                ]
            except discord.DiscordException:
                logger.exception(
                    "Failed to backfill discussion channel: channel_id=%s",
                    channel_id,
                )
                continue
            for message in messages:
                incoming = self._incoming(message, recovered=True)
                if incoming is not None:
                    await self._enqueue(incoming, channel)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.channel.id not in self._settings.channel_ids
        ):
            return
        incoming = self._incoming(message, recovered=False)
        if incoming is None:
            return
        await self._enqueue(incoming, message.channel)

    async def _enqueue(
        self,
        message: IncomingDiscussionMessage,
        channel: discord.abc.Messageable,
    ) -> None:
        queued = _QueuedMessage(message=message, channel=channel)
        task = asyncio.create_task(
            self._process_safely(queued),
            name=(
                f"discord-discussion-{message.channel_id}-{message.external_message_id}"
            ),
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_safely(self, queued: _QueuedMessage) -> None:
        try:
            await self._process(queued)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Unexpected discussion task failure: channel_id=%s",
                queued.message.channel_id,
            )

    async def _process(self, queued: _QueuedMessage) -> None:
        bot_user = self.bot.user
        if bot_user is None:
            return
        injector = cast(Any, self.bot).injector
        handler = injector.get(ProcessDiscussionMessageHandler)
        result = await handler.handle(
            ProcessDiscussionMessageCommand(
                message=queued.message,
                character_id=self._settings.character_id,
                self_external_id=str(bot_user.id),
                self_display_name=bot_user.display_name,
                sender=DiscordDiscussionMessageSender(queued.channel),
                publication_delay_seconds=self._response_delay(queued.message),
            )
        )
        if is_err(result):
            logger.error(
                "Failed to process discussion message: external_message_id=%s error=%s",
                queued.message.external_message_id,
                result.error.message,
            )

    def _response_delay(self, message: IncomingDiscussionMessage) -> float:
        if message.recovered:
            return 0.0
        delay = random.uniform(
            self._settings.response_delay_min_seconds,
            self._settings.response_delay_max_seconds,
        )
        if message.mentioned_self:
            return delay * 0.25
        return delay

    def _incoming(
        self, message: discord.Message, *, recovered: bool
    ) -> IncomingDiscussionMessage | None:
        bot_user = self.bot.user
        is_self = bot_user is not None and message.author.id == bot_user.id
        if is_self and not recovered:
            return None
        if message.webhook_id is not None:
            return None
        content = message.content.strip()
        if not content or message.guild is None:
            return None
        author_kind = (
            DiscussionAuthorKind.SELF
            if is_self
            else (
                DiscussionAuthorKind.BOT
                if message.author.bot
                else DiscussionAuthorKind.HUMAN
            )
        )
        display_name = getattr(message.author, "display_name", message.author.name)
        return IncomingDiscussionMessage(
            external_message_id=str(message.id),
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            author_external_id=str(message.author.id),
            author_display_name=str(display_name),
            author_kind=author_kind,
            text=content,
            mentioned_self=(
                bot_user is not None
                and any(user.id == bot_user.id for user in message.mentions)
            ),
            occurred_at=message.created_at,
            recovered=recovered,
        )
