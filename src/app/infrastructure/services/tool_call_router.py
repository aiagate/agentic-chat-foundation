"""Service for routing generated tool calls to execution events."""

import logging
from uuid import uuid4

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.chat_events import (
    CHAT_TOOL_REQUESTED_TOPIC,
    build_chat_tool_requested_payload,
)
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_call_router import (
    IToolCallRouter,
    ToolCallRoutingError,
    ToolCallRoutingRequest,
)
from app.contracts.ports.tool_call_store import IToolCallStore
from app.contracts.ports.tool_catalog import IToolCatalog
from app.domain.value_objects.chat_type import ChatType

logger = logging.getLogger(__name__)


class ToolCallRoutingService(IToolCallRouter):
    """Validate, store, and publish generated tool calls."""

    def __init__(
        self,
        event_bus: IEventBus,
        tool_catalog: IToolCatalog,
        tool_call_store: IToolCallStore,
    ) -> None:
        self._event_bus = event_bus
        self._tool_catalog = tool_catalog
        self._tool_call_store = tool_call_store

    async def route(
        self,
        request: ToolCallRoutingRequest,
    ) -> Result[list[str], ToolCallRoutingError]:
        if not request.tool_calls:
            return Err(ToolCallRoutingError("At least one tool call is required"))

        tool_call_ids: list[str] = []
        for raw_tool_call in request.tool_calls:
            tool_call = raw_tool_call.model_copy(
                update={
                    "tool_call_id": raw_tool_call.tool_call_id or str(uuid4()),
                    "character_id": request.character_id,
                }
            )
            if self._tool_catalog.get_tool(tool_call.tool_name) is None:
                return Err(
                    ToolCallRoutingError(
                        f"Unsupported tool call: {tool_call.tool_name}"
                    )
                )

            tool_call_id = tool_call.tool_call_id
            if tool_call_id is None:
                return Err(ToolCallRoutingError("Tool call ID was not assigned"))

            tool_call_ids.append(tool_call_id)
            try:
                save_result = await self._tool_call_store.save(tool_call)
                if is_err(save_result):
                    return Err(ToolCallRoutingError(save_result.error.message))
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
                return Err(ToolCallRoutingError("Failed to route tool calls"))

        return Ok(tool_call_ids)
