"""Short-lived tool result store port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.messages.tool_result_context import ToolResultContext


class ToolResultStoreError(Exception):
    """Represents a tool result store failure."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class IToolResultStore(ABC):
    """Store normalized tool results by tool call ID."""

    @abstractmethod
    async def save(
        self, context: ToolResultContext
    ) -> Result[None, ToolResultStoreError]:
        """Save one tool result."""
        raise NotImplementedError

    @abstractmethod
    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[ToolResultContext, ToolResultStoreError]:
        """Load one tool result."""
        raise NotImplementedError
