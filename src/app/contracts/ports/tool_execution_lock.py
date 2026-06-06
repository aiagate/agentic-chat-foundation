"""Tool execution idempotency lock port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result


class ToolExecutionLockError(Exception):
    """Represents an error while acquiring a tool execution lock."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class IToolExecutionLock(ABC):
    """Prevent duplicate execution for a short-lived tool call."""

    @abstractmethod
    async def acquire(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[bool, ToolExecutionLockError]:
        """Return true only for the first execution attempt."""
        raise NotImplementedError
