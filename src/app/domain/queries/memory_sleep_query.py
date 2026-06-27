"""メモリ睡眠の対象選定クエリ契約。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.queries.raw_chat_log_query import IRawChatLogQuery, RawChatLog


@dataclass(frozen=True, slots=True)
class MemorySleepTarget:
    """One user/day raw chat log batch selected for memory sleep."""

    user_id: str
    day: date
    raw_logs: list[RawChatLog]


class IMemorySleepQuery(ABC):
    """メモリ睡眠の対象を選定する契約。"""

    @abstractmethod
    async def list_pending_targets(
        self,
        query: IRawChatLogQuery,
        *,
        reference_time: datetime,
    ) -> list[MemorySleepTarget]:
        """対象の user/day バッチを列挙する。"""
        pass
