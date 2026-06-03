"""Tool execution port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.tool_contracts import ToolCall, ToolExecutionResult
from app.domain.value_objects.chat_type import ChatType


@dataclass(frozen=True)
class ToolExecutorError(Exception):
    """Represents a tool execution adapter error."""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ToolExecutionContext:
    """Context required to execute a tool call."""

    chat_id: str
    user_id: str
    chat_type: ChatType
    tool_call: ToolCall
    character_id: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    agent_context: AgentEnvelope | None = None


class IToolExecutor(ABC):
    """Execute a validated tool call."""

    @abstractmethod
    async def execute(
        self,
        context: ToolExecutionContext,
    ) -> Result[ToolExecutionResult, ToolExecutorError]:
        """Execute the tool and return a normalized result payload."""
        raise NotImplementedError
