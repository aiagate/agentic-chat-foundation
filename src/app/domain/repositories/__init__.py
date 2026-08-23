"""ドメイン層のリポジトリ関連公開API。"""

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery
from app.domain.repositories.interfaces import (
    ChatRecordReference,
    ICharacterRelationshipRepository,
    IChatRecordRepository,
    IMemoryConsolidatedChatSourceRepository,
    RepositoryError,
    RepositoryErrorType,
)

__all__ = [
    "ICharacterRelationshipRepository",
    "IChatRecordRepository",
    "ChatRecordReference",
    "IMemoryConsolidatedChatSourceRepository",
    "IChatHistoryQuery",
    "IRawChatLogQuery",
    "RepositoryError",
    "RepositoryErrorType",
]
