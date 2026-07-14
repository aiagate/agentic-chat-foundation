"""長期記憶整理の対象選定クエリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.queries.raw_chat_log_query import IRawChatLogQuery, RawChatLog


@dataclass(frozen=True, slots=True)
class LongTermMemoryTarget:
    """One user/day raw chat log batch selected for organization."""

    user_id: str
    day: date
    raw_logs: list[RawChatLog]


class ILongTermMemoryQuery(ABC):
    """長期記憶整理の対象を選定する契約。"""

    @abstractmethod
    async def list_pending_targets(
        self,
        query: IRawChatLogQuery,
        *,
        reference_time: datetime,
    ) -> list[LongTermMemoryTarget]:
        """対象の user/day バッチを列挙する。"""
        pass
