"""Run a single agent turn with optional retrieved context."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast, runtime_checkable

from flow_med import Mediator, Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import (
    build_reply_ready_payload,
    reply_topic_for,
)
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.conversation_context import (
    ConversationContext,
    render_conversation_context,
)
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.retrieved_context_store import IRetrievedContextStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.domain.aggregates.chat import Chat, DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_id import ChatId
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import (
    MessageContent,
    render_message_content_text,
)
from app.infrastructure.messaging.null_event_bus import NullEventBus
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.usecases.agent.route_tool_calls import RouteToolCallsCommand
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)
_SESSION_GAP_THRESHOLD = timedelta(hours=12)


@runtime_checkable
class _SessionProtocol(Protocol):
    """Subset of async session behavior needed by this use case."""

    def add(self, instance: object) -> None: ...

    async def flush(self) -> None: ...


@dataclass(frozen=True)
class RunAgentTurnResult:
    """Result metadata for one agent turn."""

    contents: list[str]
    tool_call_id: str | None = None


@dataclass
class RunAgentTurnQuery(Request[Result[RunAgentTurnResult, UseCaseError]]):
    """Run the agent runtime for one turn."""

    chat_id: str
    guild_id: str
    channel_id: str
    character_id: str
    user_id: str = "default"
    chat_type: ChatType = ChatType.DISCORD
    prompt: str | None = None
    source_request_id: str | None = None
    tool_call_id: str | None = None
    tool_failure_context: str | None = None
    agent_context: AgentEnvelope | None = None


class RunAgentTurnHandler(
    RequestHandler[RunAgentTurnQuery, Result[RunAgentTurnResult, UseCaseError]]
):
    """Handle one agent turn and re-enter the search workflow when needed."""

    @inject
    def __init__(
        self,
        ai_service: IAIService,
        retrieved_context_store: IRetrievedContextStore,
        tool_catalog: IToolCatalog,
        uow: IUnitOfWork,
        event_bus: IEventBus | None = None,
        *,
        agent_profile_service: IAgentProfileService,
    ) -> None:
        self._ai_service = ai_service
        self._agent_profile_service = agent_profile_service
        self._retrieved_context_store = retrieved_context_store
        self._tool_catalog = tool_catalog
        self._uow = uow
        self._event_bus = event_bus or NullEventBus()

    async def handle(
        self, request: RunAgentTurnQuery
    ) -> Result[RunAgentTurnResult, UseCaseError]:
        """Generate content, execute tool requests, and persist the reply."""

        async with self._uow:
            character_id = request.character_id
            agent_context = _with_character_id(request.agent_context, character_id)

            prompt_result = await self._resolve_prompt(request)
            if is_err(prompt_result):
                return Err(prompt_result.error)
            prompt = prompt_result.value

            history_result = await self._history(request)
            if is_err(history_result):
                return Err(history_result.error)
            history, conversation_context = history_result.value

            memory_result = await Mediator.send_async(
                RetrieveMemoryContextQuery(
                    history=history,
                    prompt=prompt,
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
            profile_bundle = self._agent_profile_service.load_agent_profile_bundle()
            system_parts = [
                profile_bundle.persona_context,
                render_conversation_context(conversation_context),
                memory_result.value.assembled_context,
                _output_contract_instruction(),
            ]

            if request.tool_failure_context is not None:
                system_parts.append(request.tool_failure_context)

            should_disable_web_search = False
            if request.tool_call_id is not None:
                retrieved_context_result = await self._retrieved_context_store.get(
                    request.tool_call_id,
                    character_id=character_id,
                )
                if is_err(retrieved_context_result):
                    logger.warning(
                        "Retrieved context unavailable for tool call %s: %s",
                        request.tool_call_id,
                        retrieved_context_result.error,
                    )
                else:
                    system_parts.append(retrieved_context_result.value.rendered_text)
                    if retrieved_context_result.value.tool_name == "web_search":
                        should_disable_web_search = True
                        system_parts.append(
                            "Web search results are already provided above. "
                            "Use the supplied context to answer directly and do "
                            "not call web_search again."
                        )

            tool_definitions = _filter_tool_definitions(
                self._tool_catalog.list_tools(),
                chat_type=request.chat_type,
                disable_web_search=(
                    request.tool_failure_context is not None
                    or should_disable_web_search
                ),
            )

            ai_result = await self._ai_service.generate_content(
                prompt,
                _trim_duplicate_prompt(history, prompt),
                system_instruction=_join_context(system_parts),
                tool_definitions=tool_definitions,
            )
            if is_err(ai_result):
                logger.warning(
                    "AI content generation failed: %s",
                    ai_result.error.message,
                )
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=(
                            f"Failed to generate content: {ai_result.error.message}"
                        ),
                    )
                )

            if ai_result.value.tool_calls:
                route_result = await Mediator.send_async(
                    RouteToolCallsCommand(
                        chat_id=request.chat_id,
                        source_request_id=request.source_request_id or request.chat_id,
                        guild_id=request.guild_id,
                        channel_id=request.channel_id,
                        user_id=request.user_id,
                        chat_type=request.chat_type,
                        tool_calls=ai_result.value.tool_calls,
                        character_id=character_id,
                        agent_context=agent_context,
                    )
                )
                if is_err(route_result):
                    return Err(
                        UseCaseError(
                            type=ErrorType.UNEXPECTED,
                            message="Failed to route tool request",
                        )
                    )
                return Ok(
                    RunAgentTurnResult(
                        contents=route_result.value.contents,
                        tool_call_id=request.tool_call_id,
                    )
                )

            contents = ai_result.value.contents
            match request.chat_type:
                case ChatType.LINE:
                    model_chat = LineChat.create_user_chat(
                        line_user_id=request.user_id,
                        message_content=MessageContent.texts(contents),
                    )
                case ChatType.DISCORD:
                    model_chat = DiscordChat.create(
                        guild_id=request.guild_id,
                        channel_id=request.channel_id,
                        message_content=MessageContent.texts(contents),
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
                        agent_envelope=agent_context,
                    ),
                )
            except Exception:
                logger.exception("Failed to publish chat reply event")

            return Ok(
                RunAgentTurnResult(
                    contents=contents,
                    tool_call_id=request.tool_call_id,
                )
            )

    async def _history(
        self, request: RunAgentTurnQuery
    ) -> Result[tuple[list[ChatHistoryItem], ConversationContext], UseCaseError]:
        chat_query = self._uow.GetChatHistoryQuery()
        history_result = await chat_query.get_recent_history(
            request.chat_type,
            user_id=request.user_id,
            guild_id=(
                request.guild_id if request.chat_type is ChatType.DISCORD else None
            ),
            channel_id=(
                request.channel_id if request.chat_type is ChatType.DISCORD else None
            ),
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
        current_time = datetime.now(UTC)
        session_history, conversation_context = _build_conversation_context(
            history,
            chat_type=request.chat_type,
            user_id=request.user_id,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
            current_time=current_time,
        )
        return Ok((session_history, conversation_context))

    async def _resolve_prompt(
        self,
        request: RunAgentTurnQuery,
    ) -> Result[str, UseCaseError]:
        provided_prompt = _normalize_text(request.prompt)
        if provided_prompt:
            return Ok(provided_prompt)

        chat_id_result = ChatId.from_primitive(request.chat_id)
        if is_err(chat_id_result):
            return Err(
                UseCaseError(
                    type=ErrorType.VALIDATION_ERROR,
                    message=f"Invalid chat_id: {request.chat_id}",
                )
            )

        chat_repo = self._uow.GetRepository(Chat, ChatId)
        chat_result = await chat_repo.get_by_id(chat_id_result.value)
        if is_err(chat_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=f"Failed to load chat message: {chat_result.error.message}",
                )
            )

        prompt = _chat_prompt(chat_result.value)
        if prompt is None:
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Saved chat message does not contain text content",
                )
            )
        return Ok(prompt)


def _join_context(parts: list[str | None]) -> str | None:
    rendered = [part for part in parts if part]
    if not rendered:
        return None
    return "\n\n".join(rendered)


def _output_contract_instruction() -> str:
    return (
        "Output contract:\n"
        "- Return a single JSON object that matches GeneratedContent.\n"
        "- Put normal assistant text in contents.\n"
        "- Put tool requests in tool_calls.\n"
        "- Do not serialize tool calls as a JSON array inside contents.\n"
        "- If you request a tool, keep contents empty unless you also need "
        "user-visible text."
    )


def _chat_prompt(chat: Chat) -> str | None:
    text = render_message_content_text(chat.message_content.payload)
    if text is not None:
        normalized = _normalize_text(text)
        if normalized:
            return normalized
    return None


def _trim_duplicate_prompt(
    history: Sequence[ChatHistoryItem],
    prompt: str,
) -> list[ChatHistoryItem]:
    if not history:
        return []
    if _normalize_text(history[-1].content) != _normalize_text(prompt):
        return list(history)
    if history[-1].role != "user":
        return list(history)
    return list(history[:-1])


def _build_conversation_context(
    history: Sequence[ChatHistoryItem],
    *,
    chat_type: ChatType,
    user_id: str,
    guild_id: str,
    channel_id: str,
    current_time: datetime,
) -> tuple[list[ChatHistoryItem], ConversationContext]:
    session_history, boundary = _latest_session_window(history)
    conversation_context = ConversationContext(
        chat_scope=_chat_scope_label(
            chat_type=chat_type,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        ),
        current_time=current_time,
        timezone="UTC",
        observed_message_count=len(session_history),
        has_session_boundary=boundary is not None,
        current_session_started_at=boundary[0] if boundary is not None else None,
        previous_message_at=boundary[1] if boundary is not None else None,
        gap_minutes=boundary[2] if boundary is not None else None,
    )
    return session_history, conversation_context


def _latest_session_window(
    history: Sequence[ChatHistoryItem],
) -> tuple[list[ChatHistoryItem], tuple[datetime, datetime, int] | None]:
    if not history:
        return [], None

    start_index = 0
    boundary: tuple[datetime, datetime, int] | None = None
    for index in range(1, len(history)):
        previous_at = history[index - 1].occurred_at
        current_at = history[index].occurred_at
        if previous_at is None or current_at is None:
            continue
        previous_utc = _as_utc(previous_at)
        current_utc = _as_utc(current_at)
        gap = current_utc - previous_utc
        if gap > _SESSION_GAP_THRESHOLD or current_utc.date() != previous_utc.date():
            start_index = index
            boundary = (
                current_utc,
                previous_utc,
                int(gap.total_seconds() // 60),
            )

    return list(history[start_index:]), boundary


def _chat_scope_label(
    *,
    chat_type: ChatType,
    user_id: str,
    guild_id: str,
    channel_id: str,
) -> str:
    if chat_type is ChatType.DISCORD:
        return f"DISCORD guild_id={guild_id} channel_id={channel_id} user_id={user_id}"
    return f"LINE user_id={user_id}"


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())


def _with_character_id(
    agent_context: AgentEnvelope | None,
    character_id: str,
) -> AgentEnvelope:
    if agent_context is None:
        return AgentEnvelope(character_id=character_id)
    if agent_context.character_id == character_id:
        return agent_context
    return agent_context.model_copy(update={"character_id": character_id})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _filter_tool_definitions(
    tool_definitions: list[ToolDefinition],
    *,
    chat_type: ChatType,
    disable_web_search: bool,
) -> list[ToolDefinition]:
    """Expose only the tools that make sense for the current chat type."""

    allowed_tool_names = {"memory.search", "memory.write_candidate", "web_search"}
    match chat_type:
        case ChatType.LINE:
            allowed_tool_names.add("line.reply")
        case ChatType.DISCORD:
            allowed_tool_names.update({"discord.reply", "discord.post_channel"})

    filtered_tools = [
        tool for tool in tool_definitions if tool.name in allowed_tool_names
    ]
    if disable_web_search:
        filtered_tools = [tool for tool in filtered_tools if tool.name != "web_search"]
    return filtered_tools


async def _save_generated_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    user_id: str,
) -> Result[DiscordChat | LineChat, UseCaseError]:
    """Persist a generated assistant chat as raw SQL."""

    session = getattr(uow, "_session", None)
    if not isinstance(session, _SessionProtocol):
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
