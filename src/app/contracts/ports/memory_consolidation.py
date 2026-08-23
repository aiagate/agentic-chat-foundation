"""Memory consolidation port."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.contracts.messages.memory_consolidation import MemoryConsolidationResult
from app.domain.queries.raw_chat_log_query import LongTermMemorySourceItem


class IMemoryConsolidationService(Protocol):
    """Interface for orchestration-driven memory consolidation workflows."""

    async def consolidate_chat_logs(
        self,
        *,
        user_id: str,
        day: date,
        raw_logs: list[LongTermMemorySourceItem],
        reference_time: datetime,
    ) -> MemoryConsolidationResult:
        """Consolidate one user/day raw chat log batch into long-term memory."""
        ...
