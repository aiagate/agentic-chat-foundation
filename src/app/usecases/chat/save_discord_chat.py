"""Save chat message use case."""

import logging
from dataclasses import dataclass
from typing import cast

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    DISCORD_CHAT_SAVED_TOPIC,
    build_discord_chat_saved_payload,
)
from app.contracts.ports.event_bus import IEventBus
from app.domain.aggregates.chat import DiscordChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.message_content import MessageContent
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaveChatResult:
    """Saved chat result payload."""

    id: str


@dataclass(frozen=True)
class SaveDiscordChatCommand(Request[Result[SaveChatResult, UseCaseError]]):
    """Command to persist a chat message."""

    user_id: str
    guild_id: str
    channel_id: str
    content: str


class SaveChatHandler(
    RequestHandler[SaveDiscordChatCommand, Result[SaveChatResult, UseCaseError]]
):
    """Handle SaveChatCommand."""

    @inject
    def __init__(
        self,
        uow: IUnitOfWork,
        event_bus: IEventBus,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus

    async def handle(
        self, request: SaveDiscordChatCommand
    ) -> Result[SaveChatResult, UseCaseError]:
        """Persist an incoming Discord DM chat message."""
        async with self._uow:
            add_result = await _save_raw_discord_chat(
                self._uow,
                request.user_id,
                request.guild_id,
                request.channel_id,
                request.content,
            )
            if is_err(add_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to save chat message",
                    )
                )

            commit_result = await self._uow.commit()
            if is_err(commit_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to persist chat message",
                    )
                )

            saved_chat = add_result.value
            try:
                await self._event_bus.publish(
                    DISCORD_CHAT_SAVED_TOPIC,
                    build_discord_chat_saved_payload(
                        chat_id=saved_chat.id.to_primitive(),
                        user_id=request.user_id,
                        guild_id=request.guild_id,
                        channel_id=request.channel_id,
                    ),
                )
            except Exception:
                logger.exception("Failed to publish Discord chat saved event")
            return Ok(SaveChatResult(id=saved_chat.id.to_primitive()))


async def _save_raw_discord_chat(
    uow: IUnitOfWork,
    user_id: str,
    guild_id: str,
    channel_id: str,
    content: str,
) -> Result[DiscordChat, UseCaseError]:
    """Persist a raw Discord chat row with user scope and role."""
    chat_record_repository = uow.GetChatRecordRepository()
    save_result = await chat_record_repository.add(
        DiscordChat.create(
            guild_id=guild_id,
            channel_id=channel_id,
            message_content=MessageContent.text(content),
        ),
        user_id=user_id,
        role="user",
    )
    if is_err(save_result):
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Failed to save chat message",
            )
        )
    return Ok(cast(DiscordChat, save_result.value))
