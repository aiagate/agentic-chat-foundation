"""Search workflow context store port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flow_res import Result

from app.contracts.messages.retrieved_context import RetrievedContext


class SearchContextStoreError(Exception):
    """Represents an error from the search workflow store."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class ISearchContextStore(ABC):
    """Store short-lived retrieved context by search session."""

    @abstractmethod
    async def save(
        self, context: RetrievedContext
    ) -> Result[None, SearchContextStoreError]:
        """Save retrieved context for a search session."""
        raise NotImplementedError

    @abstractmethod
    async def get(
        self, search_session_id: str
    ) -> Result[RetrievedContext, SearchContextStoreError]:
        """Load retrieved context by search session ID."""
        raise NotImplementedError
