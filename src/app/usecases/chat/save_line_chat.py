"""Save chat message use case."""

import logging
from dataclasses import dataclass
from typing import Any, cast

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    LINE_CHAT_SAVED_TOPIC,
    build_line_chat_saved_payload,
)
from app.contracts.ports.event_bus import IEventBus
from app.domain.aggregates.chat import LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.messaging.null_event_bus import NullEventBus
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SaveChatResult:
    """Saved chat result payload."""

    id: str


@dataclass(frozen=True)
class SaveLineChatCommand(Request[Result[SaveChatResult, UseCaseError]]):
    """Command to persist a chat message."""

    user_id: str
    content: str


class SaveChatHandler(
    RequestHandler[SaveLineChatCommand, Result[SaveChatResult, UseCaseError]]
):
    """Handle SaveChatCommand."""

    @inject
    def __init__(
        self,
        uow: IUnitOfWork,
        event_bus: IEventBus | None = None,
    ) -> None:
        self._uow = uow
        self._event_bus = event_bus or NullEventBus()

    async def handle(
        self, request: SaveLineChatCommand
    ) -> Result[SaveChatResult, UseCaseError]:
        """Persist an incoming Line DM chat message."""
        async with self._uow:
            add_result = await _save_raw_line_chat(
                self._uow,
                request.user_id,
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
                    LINE_CHAT_SAVED_TOPIC,
                    build_line_chat_saved_payload(
                        chat_id=saved_chat.id.to_primitive(),
                        user_id=request.user_id,
                        content=request.content,
                    ),
                )
            except Exception:
                logger.exception("Failed to publish LINE chat saved event")
            return Ok(SaveChatResult(id=saved_chat.id.to_primitive()))


async def _save_raw_line_chat(
    uow: IUnitOfWork,
    user_id: str,
    content: str,
) -> Result[LineChat, UseCaseError]:
    """Persist a raw LINE chat row with user scope and role."""
    session = cast(Any, getattr(uow, "_session", None))
    if session is None:
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Unit of work session is not available",
            )
        )

    chat_orm = cast(
        ChatORM,
        ORMMappingRegistry.to_orm(
            LineChat.create_user_chat(
                line_user_id=user_id,
                message_content=MessageContent.text(content),
            )
        ),
    )
    chat_orm.user_id = user_id
    chat_orm.role = "user"
    session.add(chat_orm)
    await session.flush()
    return Ok(cast(LineChat, ORMMappingRegistry.from_orm(chat_orm)))
