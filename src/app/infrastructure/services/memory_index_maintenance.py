"""Memory index maintenance service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flow_res import Err, Ok, Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_index import MemoryIndexRecord
from app.contracts.ports.embedding_service import IEmbeddingService
from app.contracts.ports.memory_index import MemoryIndexError
from app.contracts.ports.memory_index_maintenance import IMemoryIndexMaintenance
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    default_memory_root,
)
from app.infrastructure.queries.memory_index_query_service import (
    _stored_documents_for_scope,
    embed_memory_index_records,
    record_from_memory_index_document,
)
from app.infrastructure.repositories.memory_index_backup_repository import (
    MemoryIndexBackupRepository,
)
from app.infrastructure.repositories.memory_index_repository import (
    MemoryIndexRepository,
)


class MemoryIndexMaintenanceService(IMemoryIndexMaintenance):
    """Rebuild and repair persisted memory index rows."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        embedding_service: IEmbeddingService | None = None,
        character_id: str,
    ) -> None:
        self._root = root or default_memory_root()
        self._store = FilesystemMemoryStore(self._root)
        self._session_factory = session_factory
        self._embedding_service = embedding_service
        self._character_id = character_id

    async def rebuild_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Rebuild the persistent index rows for a scope."""

        if self._session_factory is None:
            return Err(
                MemoryIndexError("memory index session factory is not configured")
            )
        try:
            return await self._rebuild_scope_async(user_id=user_id)
        except Exception as exc:
            return Err(MemoryIndexError(str(exc)))

    async def repair_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Repair stale rows by syncing the scope from filesystem sources."""

        if self._session_factory is None:
            return Err(
                MemoryIndexError("memory index session factory is not configured")
            )
        try:
            return await self._repair_scope_async(user_id=user_id)
        except Exception as exc:
            return Err(MemoryIndexError(str(exc)))

    async def _rebuild_scope_async(
        self, *, user_id: str | None
    ) -> Result[int, MemoryIndexError]:
        session_factory = self._session_factory
        if session_factory is None:
            return Err(
                MemoryIndexError("memory index session factory is not configured")
            )
        await self._backup_scope_snapshot(user_id=user_id)
        records = await self._build_records_for_scope(user_id=user_id)
        async with session_factory() as session:
            repository = MemoryIndexRepository(session)
            await repository.delete_scope(user_id)
            changed = await repository.upsert_records(records)
            await session.commit()
        return Ok(changed)

    async def _repair_scope_async(
        self, *, user_id: str | None
    ) -> Result[int, MemoryIndexError]:
        session_factory = self._session_factory
        if session_factory is None:
            return Err(
                MemoryIndexError("memory index session factory is not configured")
            )
        await self._backup_scope_snapshot(user_id=user_id)
        records = await self._build_records_for_scope(user_id=user_id)
        async with session_factory() as session:
            repository = MemoryIndexRepository(session)
            await repository.delete_scope(user_id)
            changed = await repository.upsert_records(records)
            await session.commit()
        return Ok(changed)

    async def _backup_scope_snapshot(self, *, user_id: str | None) -> int:
        session_factory = self._session_factory
        if session_factory is None:
            return 0
        async with session_factory() as session:
            repository = MemoryIndexRepository(session)
            backup_repository = MemoryIndexBackupRepository(session)
            records = await repository.list_records(user_id)
            backed_up_at = datetime.now(UTC).isoformat()
            changed = await backup_repository.replace_scope_snapshot(
                records,
                scope_user_id=user_id,
                backed_up_at=backed_up_at,
            )
            await session.commit()
            return changed

    async def _build_records_for_scope(
        self,
        *,
        user_id: str | None,
    ) -> list[MemoryIndexRecord]:
        documents = _stored_documents_for_scope(
            self._store,
            user_id=user_id,
            character_id=self._character_id,
        )
        if not documents:
            return []
        embeddings = await embed_memory_index_records(
            [document.document for document in documents],
            embedding_service=self._embedding_service,
        )
        return [
            record_from_memory_index_document(
                document,
                embedding=embeddings[index] if index < len(embeddings) else [],
            )
            for index, document in enumerate(documents)
        ]
