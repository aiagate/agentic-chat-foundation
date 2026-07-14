"""SQLAlchemy Unit of Work implementation."""


from flow_res import Err, Ok, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.repositories import (
    IChatRecordRepository,
    IMemoryConsolidatedChatSourceRepository,
    RepositoryError,
    RepositoryErrorType,
)
from app.infrastructure.queries.chat_history_query import (
    SQLAlchemyChatHistoryQuery,
)
from app.infrastructure.queries.raw_chat_log_query import (
    SQLAlchemyRawChatLogQuery,
)
from app.infrastructure.repositories.chat_record_repository import (
    ChatRecordRepository,
)
from app.infrastructure.repositories.memory_consolidated_chat_source_repository import (
    MemoryConsolidatedChatSourceRepository,
)


class SQLAlchemyUnitOfWork(IUnitOfWork):
    """SQLAlchemy implementation of Unit of Work."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._chat_history_query: SQLAlchemyChatHistoryQuery | None = None
        self._raw_chat_log_query: SQLAlchemyRawChatLogQuery | None = None
        self._chat_record_repository: ChatRecordRepository | None = None
        self._memory_consolidated_chat_source_repository: (
            MemoryConsolidatedChatSourceRepository | None
        ) = None

    def GetChatHistoryQuery(self) -> SQLAlchemyChatHistoryQuery:
        """Get the chat history query."""
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork session not initialized. Use 'async with' context."
            )

        if self._chat_history_query is None:
            self._chat_history_query = SQLAlchemyChatHistoryQuery(self._session)

        return self._chat_history_query

    def GetRawChatLogQuery(self) -> SQLAlchemyRawChatLogQuery:
        """Get the raw chat log query."""
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork session not initialized. Use 'async with' context."
            )

        if self._raw_chat_log_query is None:
            self._raw_chat_log_query = SQLAlchemyRawChatLogQuery(self._session)

        return self._raw_chat_log_query

    def GetChatRecordRepository(self) -> IChatRecordRepository:
        """Get the chat record repository."""
        if self._session is None:
            raise RuntimeError(
                "UnitOfWork session not initialized. Use 'async with' context."
            )

        if self._chat_record_repository is None:
            self._chat_record_repository = ChatRecordRepository(self._session)

        return self._chat_record_repository

    def GetMemoryConsolidatedChatSourceRepository(
        self,
    ) -> IMemoryConsolidatedChatSourceRepository:
        """Get the memory-consolidated chat source repository."""

        if self._session is None:
            raise RuntimeError(
                "UnitOfWork session not initialized. Use 'async with' context."
            )
        if self._memory_consolidated_chat_source_repository is None:
            self._memory_consolidated_chat_source_repository = (
                MemoryConsolidatedChatSourceRepository(self._session)
            )
        return self._memory_consolidated_chat_source_repository

    async def commit(self) -> Result[None, RepositoryError]:
        """Commit the transaction."""
        if self._session is None:
            raise RuntimeError("UnitOfWork session not initialized.")
        try:
            await self._session.commit()
            return Ok(None)
        except SQLAlchemyError as e:
            return Err(
                RepositoryError(type=RepositoryErrorType.UNEXPECTED, message=str(e))
            )

    async def rollback(self) -> None:
        """Rollback the transaction."""
        if self._session is None:
            raise RuntimeError("UnitOfWork session not initialized.")
        await self._session.rollback()

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        """Enter async context manager."""
        self._session = self._session_factory()
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit async context manager with auto-rollback."""
        if self._session is None:
            return

        try:
            if exc_type is not None:
                # Exception occurred - rollback
                await self.rollback()
        finally:
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
            self._session = None
            self._chat_history_query = None
            self._raw_chat_log_query = None
            self._chat_record_repository = None
            self._memory_consolidated_chat_source_repository = None
