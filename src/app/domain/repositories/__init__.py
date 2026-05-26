"""Repository interfaces for domain layer."""

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery
from app.domain.repositories.interfaces import (
    IMemoryConsolidationRunRepository,
    IRepository,
    IRepositoryWithId,
    IUnitOfWork,
    MemoryConsolidationRunClaim,
    MemoryConsolidationRunRecord,
    MemoryConsolidationRunStatus,
    RepositoryError,
    RepositoryErrorType,
)

__all__ = [
    "IRepository",
    "IRepositoryWithId",
    "IMemoryConsolidationRunRepository",
    "IChatHistoryQuery",
    "IRawChatLogQuery",
    "IUnitOfWork",
    "MemoryConsolidationRunClaim",
    "MemoryConsolidationRunRecord",
    "MemoryConsolidationRunStatus",
    "RepositoryError",
    "RepositoryErrorType",
]
