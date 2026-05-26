"""Generate chat content using retrieved search context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from flow_med import Mediator, Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.search_context_store import ISearchContextStore
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.messaging.null_event_bus import NullEventBus
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class GenerateContentWithRetrievedContextResult:
    """Generated content payload."""

    contents: list[str]


@dataclass
class GenerateContentWithRetrievedContextQuery(
    Request[Result[GenerateContentWithRetrievedContextResult, UseCaseError]]
):
    """Generate a response with previously retrieved context."""

    prompt: str
    search_session_id: str
    guild_id: str
    channel_id: str
    user_id: str = "default"
    chat_type: ChatType = ChatType.DISCORD


class GenerateContentWithRetrievedContextHandler(
    RequestHandler[
        GenerateContentWithRetrievedContextQuery,
        Result[GenerateContentWithRetrievedContextResult, UseCaseError],
    ]
):
    """Handle post-search regeneration."""

    @inject
    def __init__(
        self,
        ai_service: IAIService,
        search_context_store: ISearchContextStore,
        uow: IUnitOfWork,
        event_bus: IEventBus | None = None,
    ) -> None:
        self._ai_service = ai_service
        self._search_context_store = search_context_store
        self._uow = uow
        self._event_bus = event_bus or NullEventBus()

    async def handle(
        self, request: GenerateContentWithRetrievedContextQuery
    ) -> Result[GenerateContentWithRetrievedContextResult, UseCaseError]:
        """Generate content using retrieved context and persist the reply."""
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
            search_context_result = await self._search_context_store.get(
                request.search_session_id
            )
            if is_err(search_context_result):
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to retrieve search context",
                    )
                )
            search_context = search_context_result.value
            system_instruction = "\n\n".join(
                part
                for part in [
                    memory_pack.assembled_context,
                    search_context.rendered_text,
                ]
                if part
            )

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
                pass

            return Ok(GenerateContentWithRetrievedContextResult(contents=contents))


def _join_contents(contents: list[str]) -> str:
    return "\n".join(content for content in contents if content)


async def _save_generated_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    user_id: str,
) -> Result[DiscordChat | LineChat, UseCaseError]:
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
