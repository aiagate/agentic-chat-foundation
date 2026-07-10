"""Repository for backed up memory index rows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.messages.memory_index import MemoryIndexRecord
from app.infrastructure.orm_models.memory_index_backup_orm import (
    MemoryIndexBackupORM,
)

_GLOBAL_SCOPE_KEY = "__all__"


class MemoryIndexBackupRepository:
    """Repository for snapshotting memory index projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_scope_snapshot(
        self,
        records: Sequence[MemoryIndexRecord],
        *,
        scope_user_id: str | None,
        backed_up_at: str,
    ) -> int:
        """Replace the latest snapshot for a scope."""

        if not records:
            return 0
        scope_key = _scope_backup_key(scope_user_id)
        table = cast(Any, MemoryIndexBackupORM).__table__
        statement = delete(table).where(table.c.scope_user_id == scope_key)
        await self._session.execute(statement)
        for record in records:
            self._session.add(
                MemoryIndexBackupORM(
                    scope_user_id=scope_key,
                    source_path=record.source_path,
                    backed_up_at=backed_up_at,
                    user_id=record.user_id,
                    memory_type=record.memory_type,
                    source_id=record.source_id,
                    title=record.title,
                    content_hash=record.content_hash,
                    indexed_text=record.indexed_text,
                    tags_json=record.tags_json,
                    status=record.status,
                    timeline_type=record.timeline_type,
                    occurred_at=record.occurred_at,
                    updated_at=record.updated_at,
                    importance=record.importance,
                    confidence=record.confidence,
                    decay_score=record.decay_score,
                    embedding=list(record.embedding),
                )
            )
        await self._session.flush()
        return len(records)


def _scope_backup_key(scope_user_id: str | None) -> str:
    if scope_user_id is None:
        return _GLOBAL_SCOPE_KEY
    return scope_user_id
