"""Periodically offer the active character an opportunity to start a topic."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, cast

import discord
from discord.ext import commands
from flow_res import is_err

from app.presentation.bot.cogs.base_cog import BaseCog
from app.presentation.bot.discord_discussion_sender import (
    DiscordDiscussionMessageSender,
)
from app.usecases.discussion.generate_autonomous_topic import (
    GenerateAutonomousTopicCommand,
    GenerateAutonomousTopicHandler,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AutonomousTopicCogSettings:
    """Scheduling configuration for one independent character process."""

    enabled: bool
    channel_ids: frozenset[int]
    character_id: str
    initial_delay_seconds: float = 300.0
    interval_seconds: float = 900.0
    publication_delay_min_seconds: float = 2.0
    publication_delay_max_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.initial_delay_seconds < 0:
            raise ValueError("initial delay must not be negative")
        if self.interval_seconds <= 0:
            raise ValueError("topic interval must be positive")
        if self.publication_delay_min_seconds < 0:
            raise ValueError("minimum publication delay must not be negative")
        if self.publication_delay_max_seconds < self.publication_delay_min_seconds:
            raise ValueError("maximum publication delay must be at least the minimum")


class AutonomousTopicCog(BaseCog, name="Autonomous Topics"):
    """Schedule local topic decisions without Redis or cross-bot coordination."""

    def __init__(
        self,
        bot: commands.Bot,
        settings: AutonomousTopicCogSettings,
    ) -> None:
        super().__init__(bot)
        self._settings = settings
        self._scheduler_task: asyncio.Task[None] | None = None

    async def cog_unload(self) -> None:
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            self._scheduler_task = None

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if (
            not self._settings.enabled
            or not self._settings.channel_ids
            or self._scheduler_task is not None
        ):
            return
        self._scheduler_task = asyncio.create_task(
            self._run_scheduler(),
            name=f"autonomous-topic-scheduler-{self._settings.character_id}",
        )
        logger.info(
            "Started autonomous topic scheduler: character_id=%s channels=%s",
            self._settings.character_id,
            sorted(self._settings.channel_ids),
        )

    async def _run_scheduler(self) -> None:
        try:
            if self._settings.initial_delay_seconds > 0:
                await asyncio.sleep(self._settings.initial_delay_seconds)
            while not self.bot.is_closed():
                for channel_id in self._settings.channel_ids:
                    await self._process_channel_safely(channel_id)
                await asyncio.sleep(self._settings.interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _process_channel_safely(self, channel_id: int) -> None:
        try:
            await self._process_channel(channel_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Unexpected autonomous topic task failure: channel_id=%s",
                channel_id,
            )

    async def _process_channel(self, channel_id: int) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.DiscordException:
                logger.exception(
                    "Failed to fetch autonomous topic channel: channel_id=%s",
                    channel_id,
                )
                return
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            logger.warning(
                "Autonomous topic channel is not a guild text channel: channel_id=%s",
                channel_id,
            )
            return
        bot_user = self.bot.user
        if bot_user is None:
            return

        injector = cast(Any, self.bot).injector
        handler = injector.get(GenerateAutonomousTopicHandler)
        result = await handler.handle(
            GenerateAutonomousTopicCommand(
                guild_id=str(channel.guild.id),
                channel_id=str(channel.id),
                character_id=self._settings.character_id,
                self_external_id=str(bot_user.id),
                self_display_name=bot_user.display_name,
                sender=DiscordDiscussionMessageSender(channel),
                publication_delay_seconds=random.uniform(
                    self._settings.publication_delay_min_seconds,
                    self._settings.publication_delay_max_seconds,
                ),
            )
        )
        if is_err(result):
            logger.error(
                "Failed to generate autonomous topic: channel_id=%s error=%s",
                channel_id,
                result.error.message,
            )
            return
        if result.value is not None:
            logger.info(
                "Autonomous topic evaluated: channel_id=%s disposition=%s",
                channel_id,
                result.value.disposition.value,
            )
