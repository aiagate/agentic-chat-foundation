"""Generate chat content using AI providers."""

import logging
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from flow_med import Mediator, Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    CHAT_SEARCH_REQUESTED_TOPIC,
    build_chat_search_requested_payload,
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.messaging.null_event_bus import NullEventBus
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerateContentResult:
    """Generated content payload."""

    contents: list[str]


@dataclass
class GenerateContentQuery(Request[Result[GenerateContentResult, UseCaseError]]):
    """Request for generating a response from AI."""

    prompt: str
    chat_id: str
    guild_id: str
    channel_id: str
    user_id: str = "default"
    chat_type: ChatType = ChatType.DISCORD


class GenerateContentHandler(
    RequestHandler[GenerateContentQuery, Result[GenerateContentResult, UseCaseError]]
):
    """Handle GenerateContentQuery."""

    @inject
    def __init__(
        self,
        ai_service: IAIService,
        uow: IUnitOfWork,
        event_bus: IEventBus | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._uow = uow
        self._event_bus = event_bus or NullEventBus()

    async def handle(
        self, request: GenerateContentQuery
    ) -> Result[GenerateContentResult, UseCaseError]:
        """Generate content and persist the model reply."""
        async with self._uow:
            chat_query = self._uow.GetChatHistoryQuery()
            history_result = await chat_query.get_recent_history(
                request.chat_type,
                limit=20,
            )
            if is_err(history_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to retrieve chat history",
                    )
                )

            history = history_result.value
            memory_result = await Mediator.send_async(
                RetrieveMemoryContextQuery(
                    query=request.prompt,
                    user_id=request.user_id,
                )
            )
            if is_err(memory_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to retrieve memory context",
                    )
                )
            memory_pack = memory_result.value
            system_instruction = memory_pack.assembled_context

            ai_result = await self._ai_service.generate_content(
                request.prompt,
                history,
                system_instruction=system_instruction,
            )
            if is_err(ai_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to generate content",
                    )
                )

            if ai_result.value.tool_use_request is not None:
                tool_use_request = ai_result.value.tool_use_request
                search_session_id = tool_use_request.search_session_id or str(uuid4())
                payload = build_chat_search_requested_payload(
                    search_session_id=search_session_id,
                    source_request_id=request.chat_id,
                    chat_id=request.chat_id,
                    user_id=request.user_id,
                    chat_type=request.chat_type.to_primitive(),
                    prompt=request.prompt,
                    query=tool_use_request.arguments.query,
                    tool_name=tool_use_request.tool_name,
                    user_message=tool_use_request.user_message,
                    max_results=tool_use_request.arguments.max_results,
                    guild_id=(
                        request.guild_id
                        if request.chat_type is ChatType.DISCORD
                        else None
                    ),
                    channel_id=(
                        request.channel_id
                        if request.chat_type is ChatType.DISCORD
                        else None
                    ),
                )
                try:
                    await self._event_bus.publish(
                        CHAT_SEARCH_REQUESTED_TOPIC,
                        payload,
                    )
                except Exception:
                    logger.exception("Failed to publish search request event")
                return Ok(
                    GenerateContentResult(contents=[tool_use_request.user_message])
                )

            contents = ai_result.value.contents
            content = _join_contents(contents)
            match request.chat_type:
                case ChatType.LINE:
                    model_chat = LineChat.create_user_chat(
                        line_user_id=request.user_id,
                        message_content=MessageContent.text(content),
                    )
                case ChatType.DISCORD:
                    model_chat = DiscordChat.create(
                        guild_id=request.guild_id,
                        channel_id=request.channel_id,
                        message_content=MessageContent.text(content),
                    )
            add_result = await _save_generated_chat(
                self._uow,
                model_chat,
                request.user_id,
            )
            if is_err(add_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to save generated content",
                    )
                )

            commit_result = await self._uow.commit()
            if is_err(commit_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to persist generated content",
                    )
                )

            try:
                await self._event_bus.publish(
                    reply_topic_for(request.chat_type),
                    build_reply_ready_payload(
                        chat_type=request.chat_type,
                        contents=contents,
                        guild_id=(
                            request.guild_id
                            if request.chat_type is ChatType.DISCORD
                            else None
                        ),
                        channel_id=(
                            request.channel_id
                            if request.chat_type is ChatType.DISCORD
                            else None
                        ),
                        user_id=(
                            request.user_id
                            if request.chat_type is ChatType.LINE
                            else None
                        ),
                    ),
                )
            except Exception:
                logger.exception("Failed to publish chat reply event")

            return Ok(GenerateContentResult(contents=contents))


def _join_contents(contents: list[str]) -> str:
    return "\n".join(content for content in contents if content)


async def _save_generated_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    user_id: str,
) -> Result[DiscordChat | LineChat, UseCaseError]:
    """Persist a generated assistant chat as raw SQL."""
    session = cast(Any, getattr(uow, "_session", None))
    if session is None:
        return Err(
            UseCaseError(
                type=ErrorType.UNEXPECTED,
                message="Unit of work session is not available",
            )
        )

    chat_orm = cast(ChatORM, ORMMappingRegistry.to_orm(chat))
    chat_orm.user_id = user_id
    chat_orm.role = "assistant"
    session.add(chat_orm)
    await session.flush()
    return Ok(cast(DiscordChat | LineChat, ORMMappingRegistry.from_orm(chat_orm)))
