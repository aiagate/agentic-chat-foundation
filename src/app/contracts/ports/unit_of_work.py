"""Application transaction boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, overload

from flow_res import Result

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery
from app.domain.repositories.interfaces import (
    IChatRecordRepository,
    IMemoryConsolidatedChatSourceRepository,
    IRepository,
    IRepositoryWithId,
    RepositoryError,
)


class IUnitOfWork(ABC):
    """Coordinate repositories and application events in one transaction."""

    @overload
    def GetRepository[T](self, entity_type: type[T]) -> IRepository[T]: ...

    @overload
    def GetRepository[T, K](
        self,
        entity_type: type[T],
        key_type: type[K],
    ) -> IRepositoryWithId[T, K]: ...

    @abstractmethod
    def GetRepository[T, K](
        self,
        entity_type: type[T],
        key_type: type[K] | None = None,
    ) -> IRepository[T] | IRepositoryWithId[T, K]:
        """Return the repository bound to the active transaction."""
        raise NotImplementedError

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
    def enqueue_event(
        self,
        topic: str,
        payload: Mapping[str, object],
        *,
        event_id: str | None = None,
    ) -> str:
        """Add an application event to the active database transaction."""
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
