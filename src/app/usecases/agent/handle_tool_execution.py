"""Execute a validated generic tool call."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import (
    CHAT_TOOL_COMPLETED_TOPIC,
    build_chat_tool_completed_payload,
)
from app.contracts.messages.tool_contracts import (
    ToolCall,
    ToolContinuation,
    ToolExecutionResult,
    normalize_reply_contents,
)
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_execution_lock import IToolExecutionLock
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.contracts.ports.tool_result_store import IToolResultStore
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.usecases.agent.turn_reply import persist_reply
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class HandleToolExecutionResult:
    """Result metadata for a handled tool execution."""

    result: dict[str, object]


@dataclass
class HandleToolExecutionCommand(
    Request[Result[HandleToolExecutionResult, UseCaseError]]
):
    """Execute a generic tool call and emit completion."""

    chat_id: str
    tool_call_id: str
    user_id: str
    chat_type: ChatType
    tool_name: str
    character_id: str
    guild_id: str | None = None
    channel_id: str | None = None
    agent_context: AgentEnvelope | None = None


class HandleToolExecutionHandler(
    RequestHandler[
        HandleToolExecutionCommand,
        Result[HandleToolExecutionResult, UseCaseError],
    ]
):
    """Execute supported tools and publish their completion event."""

    @inject
    def __init__(
        self,
        event_bus: IEventBus,
        tool_executor: IToolExecutor,
        tool_call_store: IToolCallStore,
        tool_execution_lock: IToolExecutionLock,
        tool_catalog: IToolCatalog,
        tool_result_store: IToolResultStore,
        uow: IUnitOfWork,
    ) -> None:
        self._event_bus = event_bus
        self._tool_executor = tool_executor
        self._tool_call_store = tool_call_store
        self._tool_execution_lock = tool_execution_lock
        self._tool_catalog = tool_catalog
        self._tool_result_store = tool_result_store
        self._uow = uow

    async def handle(
        self, request: HandleToolExecutionCommand
    ) -> Result[HandleToolExecutionResult, UseCaseError]:
        """Execute the tool and publish a generic completion event."""

        continuation = self._continuation(request.tool_name)
        tool_call_result = await self._tool_call_store.get(
            request.tool_call_id,
            character_id=request.character_id,
        )
        if is_err(tool_call_result):
            await self._publish_completion(
                request=request,
                status="error",
                error=tool_call_result.error.message,
                error_code="tool_call_not_found",
                tool_call=None,
                continuation=continuation,
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=tool_call_result.error.message,
                )
            )

        tool_call = tool_call_result.value
        continuation = self._continuation(tool_call.tool_name)
        execution_character_id = request.character_id
        lock_result = await self._tool_execution_lock.acquire(
            request.tool_call_id,
            character_id=execution_character_id,
        )
        if is_err(lock_result):
            await self._publish_completion(
                request=request,
                status="error",
                error=lock_result.error.message,
                error_code="tool_execution_lock_error",
                tool_call=tool_call,
                continuation=continuation,
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=lock_result.error.message,
                )
            )
        if not lock_result.value:
            return Ok(HandleToolExecutionResult(result={"duplicate": True}))

        execution_context = ToolExecutionContext(
            chat_id=request.chat_id,
            user_id=request.user_id,
            chat_type=request.chat_type,
            tool_call=tool_call,
            character_id=execution_character_id,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
            agent_context=request.agent_context,
        )
        if tool_call.tool_name in _SEND_MESSAGE_TOOL_NAMES:
            execution_result = await self._execute_send_message(execution_context)
        else:
            execution_result = await self._tool_executor.execute(execution_context)
        if is_err(execution_result):
            if continuation == "reenter":
                await self._save_error_result(
                    tool_call=tool_call,
                    character_id=execution_character_id,
                    error=execution_result.error.message,
                )
            await self._publish_completion(
                request=request,
                status="error",
                error=execution_result.error.message,
                error_code="tool_execution_error",
                tool_call=tool_call,
                continuation=continuation,
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=execution_result.error.message,
                )
            )

        result_payload = execution_result.value.result
        await self._publish_completion(
            request=request,
            status="ok",
            result=result_payload,
            tool_call=tool_call,
            continuation=continuation,
        )
        return Ok(HandleToolExecutionResult(result=result_payload))

    async def _execute_send_message(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        """Persist and publish one send-message tool invocation."""

        destination = _resolve_send_destination(context)
        if isinstance(destination, ToolExecutorError):
            return Err(destination)
        chat_type, guild_id, channel_id = destination

        contents = normalize_reply_contents(context.tool_call.arguments)
        if contents is None:
            return Err(ToolExecutorError("Tool call content must not be empty"))

        async with self._uow:
            reply_result = await persist_reply(
                uow=self._uow,
                event_bus=self._event_bus,
                chat_type=chat_type,
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=context.user_id,
                contents=contents,
                agent_context=context.tool_call,
                tool_call_id=context.tool_call.tool_call_id,
            )
        if is_err(reply_result):
            return Err(ToolExecutorError(reply_result.error.message))

        result: dict[str, object] = {"content_count": len(contents)}
        return Ok(_tool_execution_result(context, result))

    def _continuation(self, tool_name: str) -> ToolContinuation:
        definition = self._tool_catalog.get_tool(tool_name)
        if definition is not None and definition.side_effect == "send_message":
            return "terminal"
        return "reenter"

    async def _save_error_result(
        self,
        *,
        tool_call: ToolCall,
        character_id: str,
        error: str,
    ) -> None:
        if tool_call.tool_call_id is None:
            return
        await self._tool_result_store.save(
            ToolResultContext(
                tool_call_id=tool_call.tool_call_id,
                character_id=character_id,
                tool_name=tool_call.tool_name,
                status="error",
                error=error,
                rendered_text=f"{tool_call.tool_name} failed: {error}",
            )
        )

    async def _publish_completion(
        self,
        *,
        request: HandleToolExecutionCommand,
        status: str,
        result: dict[str, object] | None = None,
        error: str | None = None,
        error_code: str | None = None,
        tool_call: ToolCall | None = None,
        continuation: ToolContinuation = "terminal",
    ) -> None:
        await self._event_bus.publish(
            CHAT_TOOL_COMPLETED_TOPIC,
            build_chat_tool_completed_payload(
                chat_id=request.chat_id,
                chat_type=request.chat_type.to_primitive(),
                user_id=request.user_id,
                status=status,
                tool_name=request.tool_name,
                continuation=continuation,
                result=result,
                error=error,
                error_code=error_code,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                agent_envelope=tool_call or request.agent_context,
            ),
        )


_SEND_MESSAGE_TOOL_NAMES = {
    "line.send",
    "discord.send",
}


def _resolve_send_destination(
    context: ToolExecutionContext,
) -> tuple[ChatType, str, str] | ToolExecutorError:
    tool_name = context.tool_call.tool_name
    if tool_name == "line.send":
        if context.chat_type is not ChatType.LINE:
            return ToolExecutorError("line.send is only available for LINE chats")
        return ChatType.LINE, "LINE", context.user_id

    if context.chat_type is not ChatType.DISCORD:
        return ToolExecutorError(f"{tool_name} is only available for Discord chats")

    if tool_name == "discord.send":
        if not context.channel_id:
            return ToolExecutorError("Discord send requires a channel_id")
        return ChatType.DISCORD, context.guild_id or "DM", context.channel_id
    return ToolExecutorError(f"Unsupported send tool: {tool_name}")


def _tool_execution_result(
    context: ToolExecutionContext,
    result: dict[str, object],
) -> ToolExecutionResult:
    tool_call = context.tool_call
    return ToolExecutionResult(
        event_id=tool_call.event_id,
        correlation_id=tool_call.correlation_id,
        causation_id=tool_call.causation_id,
        agent_run_id=tool_call.agent_run_id,
        agent_turn_id=tool_call.agent_turn_id,
        character_id=context.character_id,
        tool_call_id=tool_call.tool_call_id,
        source_message_id=tool_call.source_message_id,
        decision_summary=tool_call.decision_summary,
        tool_name=tool_call.tool_name,
        status="ok",
        result=result,
    )
