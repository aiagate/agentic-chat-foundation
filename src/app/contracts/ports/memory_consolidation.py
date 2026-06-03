"""Memory consolidation port."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import RawChatLog


class IMemoryConsolidationService(Protocol):
    """Interface for orchestration-driven memory consolidation workflows."""

    async def consolidate_chat_logs(
        self,
        store: IMemoryStore,
        *,
        user_id: str,
        day: date,
        raw_logs: list[RawChatLog],
        reference_time: datetime,
    ) -> int:
        """Consolidate one user/day raw chat log batch into long-term memory."""
        ...
