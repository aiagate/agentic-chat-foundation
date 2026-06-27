"""Repository for the memory-consolidated chat source projection."""

from __future__ import annotations

from datetime import datetime

from flow_res import Err, Ok, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories import (
    IMemoryConsolidatedChatSourceRepository,
    RepositoryError,
    RepositoryErrorType,
)
from app.infrastructure.orm_models.memory_consolidated_chat_source_orm import (
    MemoryConsolidatedChatSourceORM,
)


class MemoryConsolidatedChatSourceRepository(
    IMemoryConsolidatedChatSourceRepository
):
    """Persist the exact chat rows completed by memory consolidation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_consolidated(
        self,
        chat_ids: list[str],
        *,
        consolidated_at: datetime,
    ) -> Result[int, RepositoryError]:
        """Idempotently mark chat rows as consolidated."""

        unique_chat_ids = list(dict.fromkeys(chat_ids))
        try:
            for chat_id in unique_chat_ids:
                await self._session.merge(
                    MemoryConsolidatedChatSourceORM(
                        chat_id=chat_id,
                        consolidated_at=consolidated_at,
                    )
                )
            await self._session.flush()
            return Ok(len(unique_chat_ids))
        except SQLAlchemyError as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )
