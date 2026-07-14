"""ドメイン層のクエリ契約。"""

from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.queries.long_term_memory_query import (
    ILongTermMemoryQuery,
    LongTermMemoryTarget,
)
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery

__all__ = [
    "IChatHistoryQuery",
    "ILongTermMemoryQuery",
    "IRawChatLogQuery",
    "LongTermMemoryTarget",
]
