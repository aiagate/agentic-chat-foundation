"""Tool call store port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.messages.tool_contracts import ToolCall


class ToolCallStoreError(Exception):
    """Represents an error from the tool call store."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class IToolCallStore(ABC):
    """Store short-lived tool calls by tool call ID."""

    @abstractmethod
    async def save(self, tool_call: ToolCall) -> Result[None, ToolCallStoreError]:
        """Save a tool call for later execution."""
        raise NotImplementedError

    @abstractmethod
    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[ToolCall, ToolCallStoreError]:
        """Load a tool call by ID."""
        raise NotImplementedError
