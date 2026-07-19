"""Application transaction boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from flow_res import Result

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery
from app.domain.repositories.interfaces import (
    ICharacterRelationshipRepository,
    IChatRecordRepository,
    IMemoryConsolidatedChatSourceRepository,
    RepositoryError,
)


class IUnitOfWorkFactory(Protocol):
    """Create an independent transaction boundary for one operation."""

    def create(self) -> IUnitOfWork:
        """Return a fresh, request-local unit of work."""
        ...


class IUnitOfWork(ABC):
    """Coordinate the small set of repositories in one transaction."""

    @abstractmethod
    def GetChatHistoryQuery(self) -> IChatHistoryQuery:
        """Return the chat history query bound to the active transaction."""
        raise NotImplementedError

    @abstractmethod
    def GetRawChatLogQuery(self) -> IRawChatLogQuery:
        """Return the raw chat query bound to the active transaction."""
        raise NotImplementedError

    @abstractmethod
    def GetChatRecordRepository(self) -> IChatRecordRepository:
        """Return the chat writer bound to the active transaction."""
        raise NotImplementedError

    @abstractmethod
    def GetMemoryConsolidatedChatSourceRepository(
        self,
    ) -> IMemoryConsolidatedChatSourceRepository:
        """Return the memory projection writer for the transaction."""
        raise NotImplementedError

    @abstractmethod
    def GetCharacterRelationshipRepository(
        self,
    ) -> ICharacterRelationshipRepository:
        """Return the character relationship writer for the transaction."""

        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> Result[None, RepositoryError]:
        """Commit all writes in the active transaction."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back all writes in the active transaction."""
        raise NotImplementedError

    @abstractmethod
    async def __aenter__(self) -> IUnitOfWork:
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        raise NotImplementedError
