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
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_execution_lock import IToolExecutionLock
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
)
from app.domain.value_objects.chat_type import ChatType
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
    character_id: str | None = None
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
    ) -> None:
        self._event_bus = event_bus
        self._tool_executor = tool_executor
        self._tool_call_store = tool_call_store
        self._tool_execution_lock = tool_execution_lock

    async def handle(
        self, request: HandleToolExecutionCommand
    ) -> Result[HandleToolExecutionResult, UseCaseError]:
        """Execute the tool and publish a generic completion event."""

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
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=tool_call_result.error.message,
                )
            )

        tool_call = tool_call_result.value
        execution_character_id = (
            request.character_id
            or tool_call.character_id
            or (
                request.agent_context.character_id
                if request.agent_context is not None
                else None
            )
        )
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
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=lock_result.error.message,
                )
            )
        if not lock_result.value:
            return Ok(HandleToolExecutionResult(result={"duplicate": True}))

        execution_result = await self._tool_executor.execute(
            ToolExecutionContext(
                chat_id=request.chat_id,
                user_id=request.user_id,
                chat_type=request.chat_type,
                tool_call=tool_call,
                character_id=execution_character_id,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                agent_context=request.agent_context,
            )
        )
        if is_err(execution_result):
            await self._publish_completion(
                request=request,
                status="error",
                error=execution_result.error.message,
                error_code="tool_execution_error",
                tool_call=tool_call,
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
        )
        return Ok(HandleToolExecutionResult(result=result_payload))

    async def _publish_completion(
        self,
        *,
        request: HandleToolExecutionCommand,
        status: str,
        result: dict[str, object] | None = None,
        error: str | None = None,
        error_code: str | None = None,
        tool_call: ToolCall | None = None,
    ) -> None:
        await self._event_bus.publish(
            CHAT_TOOL_COMPLETED_TOPIC,
            build_chat_tool_completed_payload(
                chat_id=request.chat_id,
                chat_type=request.chat_type.to_primitive(),
                user_id=request.user_id,
                status=status,
                tool_name=request.tool_name,
                result=result,
                error=error,
                error_code=error_code,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                agent_envelope=tool_call or request.agent_context,
            ),
        )
