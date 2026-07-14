"""Synchronize the derived memory search projection after a memory write."""

from __future__ import annotations

from pathlib import Path

from flow_res import Err, Ok, Result
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_index import MemoryIndexRecord
from app.contracts.ports.embedding_service import IEmbeddingService
from app.contracts.ports.memory_index_projection import (
    IMemoryIndexProjection,
    MemoryIndexError,
)
from app.infrastructure.memory.index_projection import (
    collect_memory_index_documents,
    embed_memory_index_records,
    record_from_memory_index_document,
)
from app.infrastructure.memory.store import FilesystemMemoryStore, default_memory_root
from app.infrastructure.repositories.memory_index_repository import (
    MemoryIndexRepository,
)


class MemoryIndexProjectionService(IMemoryIndexProjection):
    """Refresh one user's derived search rows without backup or recovery state."""

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

    async def refresh_for_user(
        self,
        *,
        user_id: str,
    ) -> Result[int, MemoryIndexError]:
        if self._session_factory is None:
            return Err(MemoryIndexError("memory index session factory is not configured"))
        try:
            records = await self._build_records(user_id=user_id)
            async with self._session_factory() as session:
                repository = MemoryIndexRepository(session)
                await repository.delete_by_user_id(user_id)
                changed = await repository.upsert_records(records)
                await session.commit()
            return Ok(changed)
        except Exception as exc:
            return Err(MemoryIndexError(str(exc)))

    async def _build_records(self, *, user_id: str) -> list[MemoryIndexRecord]:
        documents = collect_memory_index_documents(
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
