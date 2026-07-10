"""Port for publishing normalized tool completion events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.contracts.messages.agentic import AgentEnvelope
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import (
    ToolContinuation,
    ToolExecutionStatus,
)


@dataclass(frozen=True, slots=True)
class ToolCompletionNotification:
    """Normalized outcome of one tool execution attempt."""

    chat_id: str
    chat_type: ChatType
    user_id: str | None
    tool_name: str
    continuation: ToolContinuation
    status: ToolExecutionStatus
    guild_id: str | None = None
    channel_id: str | None = None
    agent_context: AgentEnvelope | None = None
    result: dict[str, object] | None = None
    error: str | None = None
    error_code: str | None = None


class IToolCompletionNotifier(ABC):
    """Publish tool execution outcomes to the agent event flow."""

    @abstractmethod
    async def notify(self, notification: ToolCompletionNotification) -> None:
        """Publish one normalized completion notification."""
