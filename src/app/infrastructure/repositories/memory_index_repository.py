"""Repository for persisted memory index rows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.messages.memory_index import MemoryIndexRecord
from app.infrastructure.orm_models.memory_index_orm import MemoryIndexDocumentORM

_source_path = cast(Any, MemoryIndexDocumentORM.source_path)
_user_id = cast(Any, MemoryIndexDocumentORM.user_id)


class MemoryIndexRepository:
    """Repository for memory index projections in the main database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all_records(self) -> list[MemoryIndexRecord]:
        """Return all persisted projection rows."""

        result = await self._session.execute(
            select(MemoryIndexDocumentORM).order_by(_source_path)
        )
        return [self._to_record(orm) for orm in result.scalars().all()]

    async def list_by_user_id(self, user_id: str) -> list[MemoryIndexRecord]:
        """Return rows whose persisted user ID exactly matches the input."""

        result = await self._session.execute(
            select(MemoryIndexDocumentORM)
            .where(_user_id == user_id)
            .order_by(_source_path)
        )
        return [self._to_record(orm) for orm in result.scalars().all()]

    async def list_by_source_path_prefix(
        self,
        source_path_prefix: str,
    ) -> list[MemoryIndexRecord]:
        """Return rows below one persisted source-path prefix."""

        escaped_prefix = _escape_like(source_path_prefix)
        result = await self._session.execute(
            select(MemoryIndexDocumentORM)
            .where(_source_path.like(f"{escaped_prefix}%", escape="\\"))
            .order_by(_source_path)
        )
        return [self._to_record(orm) for orm in result.scalars().all()]

    async def upsert_records(
        self,
        records: Sequence[MemoryIndexRecord],
    ) -> int:
        """Persist rows by source path."""

        count = 0
        for record in records:
            orm = self._to_orm(record)
            await self._session.merge(orm)
            count += 1
        await self._session.flush()
        return count

    async def delete_all_records(self) -> int:
        """Delete every projection row."""

        statement = delete(MemoryIndexDocumentORM)
        result = await self._session.execute(statement)
        await self._session.flush()
        return int(cast(Any, result).rowcount or 0)

    async def delete_by_user_id(self, user_id: str) -> int:
        """Delete rows whose persisted user ID exactly matches the input."""

        statement = delete(MemoryIndexDocumentORM).where(_user_id == user_id)
        result = await self._session.execute(statement)
        await self._session.flush()
        return int(cast(Any, result).rowcount or 0)

    @staticmethod
    def _to_orm(record: MemoryIndexRecord) -> MemoryIndexDocumentORM:
        return MemoryIndexDocumentORM(
            source_path=record.source_path,
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
            embedding=record.embedding,
        )

    @staticmethod
    def _to_record(orm: MemoryIndexDocumentORM) -> MemoryIndexRecord:
        return MemoryIndexRecord(
            source_path=orm.source_path,
            source_id=orm.source_id,
            user_id=orm.user_id,
            memory_type=orm.memory_type,
            title=orm.title,
            content_hash=orm.content_hash,
            indexed_text=orm.indexed_text,
            tags_json=orm.tags_json,
            status=orm.status,
            timeline_type=orm.timeline_type,
            occurred_at=orm.occurred_at,
            updated_at=orm.updated_at,
            importance=float(orm.importance),
            confidence=float(orm.confidence),
            decay_score=float(orm.decay_score),
            embedding=list(orm.embedding or []),
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
