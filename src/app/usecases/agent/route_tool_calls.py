"""Route validated agent tool calls into tool-request events."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_events import (
    CHAT_TOOL_REQUESTED_TOPIC,
    build_chat_tool_requested_payload,
)
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.domain.value_objects.chat_type import ChatType
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteToolCallsResult:
    """Result metadata for routed tool calls."""

    tool_call_ids: list[str]


@dataclass
class RouteToolCallsCommand(Request[Result[RouteToolCallsResult, UseCaseError]]):
    """Validated tool calls emitted by the LLM for routing."""

    chat_id: str
    guild_id: str
    channel_id: str
    character_id: str
    user_id: str
    chat_type: ChatType
    tool_calls: list[ToolCall]
    source_request_id: str | None = None
    agent_context: AgentEnvelope | None = None


class RouteToolCallsHandler(
    RequestHandler[
        RouteToolCallsCommand,
        Result[RouteToolCallsResult, UseCaseError],
    ]
):
    """Convert validated tool calls into generic tool-request events."""

    @inject
    def __init__(
        self,
        event_bus: IEventBus,
        tool_catalog: IToolCatalog,
        tool_call_store: IToolCallStore,
    ) -> None:
        self._event_bus = event_bus
        self._tool_catalog = tool_catalog
        self._tool_call_store = tool_call_store

    async def handle(
        self, request: RouteToolCallsCommand
    ) -> Result[RouteToolCallsResult, UseCaseError]:
        """Validate tool calls and publish them to the event bus."""

        if not request.tool_calls:
            return Err(
                UseCaseError(
                    type=ErrorType.VALIDATION_ERROR,
                    message="At least one tool call is required",
                )
            )

        tool_call_ids: list[str] = []
        for raw_tool_call in request.tool_calls:
            tool_call = _with_tool_call_metadata(
                raw_tool_call,
                character_id=request.character_id,
            )
            validation_error = _validate_tool_call(
                tool_call,
                tool_catalog=self._tool_catalog,
            )
            if validation_error is not None:
                return Err(validation_error)

            tool_call_id = tool_call.tool_call_id
            if tool_call_id is None:
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Tool call ID was not assigned",
                    )
                )

            tool_call_ids.append(tool_call_id)
            try:
                save_result = await self._tool_call_store.save(tool_call)
                if is_err(save_result):
                    return Err(
                        UseCaseError(
                            type=ErrorType.UNEXPECTED,
                            message=save_result.error.message,
                        )
                    )
                await self._event_bus.publish(
                    CHAT_TOOL_REQUESTED_TOPIC,
                    build_chat_tool_requested_payload(
                        chat_id=request.chat_id,
                        user_id=request.user_id,
                        chat_type=request.chat_type.to_primitive(),
                        tool_call_id=tool_call_id,
                        tool_name=tool_call.tool_name,
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
                        agent_envelope=tool_call,
                    ),
                )
            except Exception:
                logger.exception("Failed to publish tool request event")
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to route tool calls",
                    )
                )

        return Ok(RouteToolCallsResult(tool_call_ids=tool_call_ids))


def _validate_tool_call(
    tool_call: ToolCall,
    *,
    tool_catalog: IToolCatalog,
) -> UseCaseError | None:
    if tool_catalog.get_tool(tool_call.tool_name) is None:
        return UseCaseError(
            type=ErrorType.VALIDATION_ERROR,
            message=f"Unsupported tool call: {tool_call.tool_name}",
        )

    return None


def _with_tool_call_id(tool_call: ToolCall) -> ToolCall:
    if tool_call.tool_call_id:
        return tool_call
    return tool_call.model_copy(update={"tool_call_id": str(uuid4())})


def _with_tool_call_metadata(
    tool_call: ToolCall,
    *,
    character_id: str,
) -> ToolCall:
    updated = _with_tool_call_id(tool_call)
    if updated.character_id == character_id:
        return updated
    return updated.model_copy(update={"character_id": character_id})
