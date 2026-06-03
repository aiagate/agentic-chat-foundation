"""Retrieved context store port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.messages.retrieved_context import RetrievedContext


class RetrievedContextStoreError(Exception):
    """Represents an error from the retrieved context store."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class IRetrievedContextStore(ABC):
    """Store short-lived retrieved context by tool call."""

    @abstractmethod
    async def save(
        self, context: RetrievedContext
    ) -> Result[None, RetrievedContextStoreError]:
        """Save retrieved context for a tool call."""
        raise NotImplementedError

    @abstractmethod
    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[RetrievedContext, RetrievedContextStoreError]:
        """Load retrieved context by tool call ID."""
        raise NotImplementedError
