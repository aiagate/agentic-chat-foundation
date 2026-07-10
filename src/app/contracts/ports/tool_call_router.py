"""Port for routing generated tool calls to execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.tool_contracts import ToolCall
from app.domain.value_objects.chat_type import ChatType


@dataclass(frozen=True, slots=True)
class ToolCallRoutingRequest:
    """Context required to validate and route generated tool calls."""

    chat_id: str
    guild_id: str
    channel_id: str
    character_id: str
    user_id: str
    chat_type: ChatType
    tool_calls: list[ToolCall]
    source_request_id: str | None = None
    agent_context: AgentEnvelope | None = None


@dataclass(frozen=True, slots=True)
class ToolCallRoutingError(Exception):
    """Failure while validating, storing, or publishing tool calls."""

    message: str


class IToolCallRouter(ABC):
    """Validate and route generated tool calls to their execution channel."""

    @abstractmethod
    async def route(
        self,
        request: ToolCallRoutingRequest,
    ) -> Result[list[str], ToolCallRoutingError]:
        """Route tool calls and return their assigned IDs."""
