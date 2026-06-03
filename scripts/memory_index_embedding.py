"""Utility for rebuilding the memory index projection."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.contracts.ports.embedding_service import IEmbeddingService
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.orm_models.memory_index_orm import MemoryIndexDocumentORM
from app.infrastructure.queries.memory_index_query_service import (
    _stored_documents_for_scope,
    embed_memory_index_records,
    record_from_memory_index_document,
)
from app.infrastructure.repositories.memory_index_repository import (
    MemoryIndexRepository,
)


async def _rebuild_index_projection(
    *,
    memory_root: Path,
    index_db: Path,
    user_id: str | None,
    embedding_service: IEmbeddingService | None,
) -> int:
    """Rebuild the SQLite memory index projection for a scope."""

    _ = MemoryIndexDocumentORM
    engine = create_async_engine(f"sqlite+aiosqlite:///{index_db}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    store = FilesystemMemoryStore(memory_root)
    documents = _stored_documents_for_scope(store, user_id=user_id)
    if not documents:
        return 0

    embeddings = await embed_memory_index_records(
        [document.document for document in documents],
        embedding_service=embedding_service,
    )
    records = [
        record_from_memory_index_document(
            document,
            embedding=embeddings[index] if index < len(embeddings) else [],
        )
        for index, document in enumerate(documents)
    ]

    async with session_factory() as session:
        repository = MemoryIndexRepository(session)
        await repository.delete_scope(user_id)
        changed = await repository.upsert_records(records)
        await session.commit()
    await engine.dispose()
    return changed
