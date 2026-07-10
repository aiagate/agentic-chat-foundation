"""Execute a validated generic tool call."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.tool_contracts import (
    ToolContinuation,
    ToolExecutionResult,
)
from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.contracts.ports.tool_completion_notifier import (
    IToolCompletionNotifier,
    ToolCompletionNotification,
)
from app.contracts.ports.tool_execution_lock import IToolExecutionLock
from app.contracts.ports.tool_executor import (
    IToolExecutor,
    ToolExecutionContext,
    ToolExecutorError,
)
from app.domain.value_objects.chat_type import ChatType


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
        tool_executor: IToolExecutor,
        tool_call_store: IToolCallStore,
        tool_execution_lock: IToolExecutionLock,
        tool_catalog: IToolCatalog,
        tool_completion_notifier: IToolCompletionNotifier,
    ) -> None:
        self._tool_executor = tool_executor
        self._tool_call_store = tool_call_store
        self._tool_execution_lock = tool_execution_lock
        self._tool_catalog = tool_catalog
        self._tool_completion_notifier = tool_completion_notifier

    async def handle(
        self, request: HandleToolExecutionCommand
    ) -> Result[HandleToolExecutionResult, UseCaseError]:
        """Execute the tool and publish a generic completion event."""

        definition = self._tool_catalog.get_tool(request.tool_name)
        continuation: ToolContinuation = (
            "terminal"
            if definition is not None and definition.side_effect == "send_message"
            else "reenter"
        )
        tool_call_result = await self._tool_call_store.get(
            request.tool_call_id,
            character_id=request.character_id,
        )
        if is_err(tool_call_result):
            await self._tool_completion_notifier.notify(
                ToolCompletionNotification(
                    chat_id=request.chat_id,
                    chat_type=request.chat_type,
                    user_id=request.user_id,
                    status="error",
                    tool_name=request.tool_name,
                    continuation=continuation,
                    error=tool_call_result.error.message,
                    error_code="tool_call_not_found",
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    agent_context=request.agent_context,
                ),
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=tool_call_result.error.message,
                )
            )

        tool_call = tool_call_result.value
        definition = self._tool_catalog.get_tool(tool_call.tool_name)
        continuation = (
            "terminal"
            if definition is not None and definition.side_effect == "send_message"
            else "reenter"
        )
        execution_character_id = request.character_id
        lock_result = await self._tool_execution_lock.acquire(
            request.tool_call_id,
            character_id=execution_character_id,
        )
        if is_err(lock_result):
            await self._tool_completion_notifier.notify(
                ToolCompletionNotification(
                    chat_id=request.chat_id,
                    chat_type=request.chat_type,
                    user_id=request.user_id,
                    status="error",
                    tool_name=request.tool_name,
                    continuation=continuation,
                    error=lock_result.error.message,
                    error_code="tool_execution_lock_error",
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    agent_context=tool_call,
                ),
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
        execution_result: Result[ToolExecutionResult, ToolExecutorError]
        execution_result = await self._tool_executor.execute(execution_context)
        if is_err(execution_result):
            await self._tool_completion_notifier.notify(
                ToolCompletionNotification(
                    chat_id=request.chat_id,
                    chat_type=request.chat_type,
                    user_id=request.user_id,
                    status="error",
                    tool_name=request.tool_name,
                    continuation=continuation,
                    error=execution_result.error.message,
                    error_code="tool_execution_error",
                    guild_id=request.guild_id,
                    channel_id=request.channel_id,
                    agent_context=tool_call,
                ),
            )
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=execution_result.error.message,
                )
            )

        result_payload = execution_result.value.result
        await self._tool_completion_notifier.notify(
            ToolCompletionNotification(
                chat_id=request.chat_id,
                chat_type=request.chat_type,
                user_id=request.user_id,
                status="ok",
                tool_name=request.tool_name,
                continuation=continuation,
                result=result_payload,
                guild_id=request.guild_id,
                channel_id=request.channel_id,
                agent_context=tool_call,
            ),
        )
        return Ok(HandleToolExecutionResult(result=result_payload))
