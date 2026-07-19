"""Main-database-backed memory index projection query."""

from __future__ import annotations

from pathlib import Path

from flow_res import Err, Ok, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_index import MemoryIndexDocument, MemoryIndexRecord
from app.contracts.ports.memory_index_query import (
    IMemoryIndexQuery,
    MemoryIndexQueryError,
)
from app.infrastructure.memory.markdown import MemoryMarkdownError
from app.infrastructure.memory.store import FilesystemMemoryStore, MemoryStoreError
from app.infrastructure.repositories.memory_index_repository import (
    MemoryIndexRepository,
)


class SQLAlchemyMemoryIndexQuery(IMemoryIndexQuery):
    """Resolve Markdown documents selected by the main DB projection."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        store: FilesystemMemoryStore,
    ) -> None:
        self._session_factory = session_factory
        self._store = store

    async def list_documents(
        self,
        *,
        user_id: str,
    ) -> Result[list[MemoryIndexDocument], MemoryIndexQueryError]:
        """Load the projected records for one exact user scope."""

        try:
            async with self._session_factory() as session:
                repository = MemoryIndexRepository(session)
                user_records = await repository.list_by_user_id(user_id)
            records = _deduplicate_records(user_records)
            documents = [self._load_document(record) for record in records]
            return Ok(
                [document for document in documents if _is_visible_document(document)]
            )
        except (
            MemoryMarkdownError,
            MemoryStoreError,
            OSError,
            SQLAlchemyError,
            ValueError,
        ) as exc:
            return Err(MemoryIndexQueryError(str(exc)))

    def _load_document(self, record: MemoryIndexRecord) -> MemoryIndexDocument:
        path = _resolve_projected_path(self._store.root, record.source_path)
        document = self._store.read_document(
            path,
            expected_memory_type=record.memory_type,
            expected_user_id=record.user_id,
        )
        return MemoryIndexDocument(
            path=path,
            reference=record.source_path,
            document=document,
            embedding=list(record.embedding),
        )


def _deduplicate_records(records: list[MemoryIndexRecord]) -> list[MemoryIndexRecord]:
    by_source_path = {record.source_path: record for record in records}
    return [by_source_path[path] for path in sorted(by_source_path)]


def _resolve_projected_path(root: Path, source_path: str) -> Path:
    resolved_root = root.resolve()
    resolved_path = (resolved_root / source_path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"Memory projection path escapes the configured root: {source_path!r}"
        ) from exc
    return resolved_path


def _is_visible_document(
    document: MemoryIndexDocument,
) -> bool:
    if document.document.front_matter.get("memory_type") != "entity":
        return True
    return document.document.front_matter.get("entity_type") != "relationship"
