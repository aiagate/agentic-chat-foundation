"""Save chat message use case."""

from dataclasses import dataclass
from typing import cast

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    LINE_CHAT_SAVED_TOPIC,
    build_line_chat_saved_payload,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.aggregates.chat import LineChat
from app.domain.value_objects.message_content import MessageContent


@dataclass(frozen=True)
class SaveLineChatResult:
    """Saved chat result payload."""

    id: str


@dataclass(frozen=True)
class SaveLineChatCommand(Request[Result[SaveLineChatResult, UseCaseError]]):
    """Command to persist a chat message."""

    user_id: str
    content: str


class SaveLineChatHandler(
    RequestHandler[SaveLineChatCommand, Result[SaveLineChatResult, UseCaseError]]
):
    """Handle SaveChatCommand."""

    @inject
    def __init__(
        self,
        uow: IUnitOfWork,
    ) -> None:
        self._uow = uow

    async def handle(
        self, request: SaveLineChatCommand
    ) -> Result[SaveLineChatResult, UseCaseError]:
        """Persist an incoming Line DM chat message."""
        async with self._uow:
            chat_record_repository = self._uow.GetChatRecordRepository()
            add_result = await chat_record_repository.add(
                LineChat.create_user_chat(
                    line_user_id=request.user_id,
                    message_content=MessageContent.text(request.content),
                ),
                user_id=request.user_id,
                role="user",
            )
            if is_err(add_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to save chat message",
                    )
                )

            saved_chat = cast(LineChat, add_result.value)
            self._uow.enqueue_event(
                LINE_CHAT_SAVED_TOPIC,
                build_line_chat_saved_payload(
                    chat_id=saved_chat.id.to_primitive(),
                    user_id=request.user_id,
                ),
            )
            commit_result = await self._uow.commit()
            if is_err(commit_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to persist chat message",
                    )
                )

            return Ok(SaveLineChatResult(id=saved_chat.id.to_primitive()))
