"""Memory consolidation port."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import IRawChatLogQuery


class IMemoryConsolidationService(Protocol):
    """Interface for deterministic memory consolidation workflows."""

    def consolidate_daily_timeline(
        self,
        store: IMemoryStore,
        *,
        user_id: str,
        day: date,
        reference_time: datetime | None = None,
    ) -> Any:
        """Consolidate raw timeline records into a daily summary."""
        ...

    async def run_memory_sleep(
        self,
        store: IMemoryStore,
        *,
        reference_time: datetime | None = None,
        raw_chat_log_query: IRawChatLogQuery | None = None,
    ) -> int:
        """Run the scheduled sleep job for all pending raw chat logs."""
        ...
