"""Tests for the main DB memory-index projection read path."""

from __future__ import annotations

from pathlib import Path

import pytest
from flow_res import is_err
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_index import MemoryIndexRecord
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.queries.memory_index_projection_query import (
    SQLAlchemyMemoryIndexQuery,
)
from app.infrastructure.repositories.memory_index_repository import (
    MemoryIndexRepository,
)
from app.infrastructure.services.memory_index_projection import (
    MemoryIndexProjectionService,
)


@pytest.mark.anyio
async def test_projection_query_returns_only_exact_user_records(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """The query should compose scopes without leaking another user's rows."""

    store = FilesystemMemoryStore(tmp_path / "memory")
    user_path = store.entity_path("u1", "desk")
    other_path = store.entity_path("u2", "private")
    _write_entity(store, user_path, user_id="u1", entity_id="desk")
    _write_entity(store, other_path, user_id="u2", entity_id="private")

    records = [
        _record(store, user_path, user_id="u1", memory_type="entity", source_id="desk"),
        _record(
            store,
            other_path,
            user_id="u2",
            memory_type="entity",
            source_id="private",
        ),
    ]
    async with session_factory() as session:
        await MemoryIndexRepository(session).upsert_records(records)
        await session.commit()

    result = await SQLAlchemyMemoryIndexQuery(session_factory, store).list_documents(
        user_id="u1",
    )

    assert not is_err(result)
    assert [document.reference for document in result.value] == ["entities/u1/desk.md"]


@pytest.mark.anyio
async def test_projection_query_reports_stale_missing_source(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """A stale projection row must be an error, not a filesystem scan fallback."""

    async with session_factory() as session:
        await MemoryIndexRepository(session).upsert_records(
            [
                _raw_record(
                    source_path="entities/u1/missing.md",
                    user_id="u1",
                    memory_type="entity",
                    source_id="missing",
                )
            ]
        )
        await session.commit()

    result = await SQLAlchemyMemoryIndexQuery(
        session_factory,
        FilesystemMemoryStore(tmp_path / "memory"),
    ).list_documents(
        user_id="u1",
    )

    assert is_err(result)
    assert "failed to read memory document" in str(result.error)


@pytest.mark.anyio
async def test_projection_service_applies_exact_path_delta(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    store = FilesystemMemoryStore(tmp_path / "memory")
    changed_path = store.entity_path("u1", "changed")
    stale_path = store.entity_path("u1", "stale")
    preserved_path = store.entity_path("u1", "preserved")
    _write_entity(store, changed_path, user_id="u1", entity_id="changed")
    async with session_factory() as session:
        await MemoryIndexRepository(session).upsert_records(
            [
                _record(
                    store,
                    stale_path,
                    user_id="u1",
                    memory_type="entity",
                    source_id="stale",
                ),
                _record(
                    store,
                    preserved_path,
                    user_id="u1",
                    memory_type="entity",
                    source_id="preserved",
                ),
            ]
        )
        await session.commit()

    result = await MemoryIndexProjectionService(
        root=store.root,
        session_factory=session_factory,
    ).apply_changes(
        user_id="u1",
        upsert_paths=[changed_path],
        delete_paths=[stale_path],
    )

    assert not is_err(result)
    async with session_factory() as session:
        records = await MemoryIndexRepository(session).list_by_user_id("u1")
    assert [record.source_id for record in records] == ["changed", "preserved"]


def _write_entity(
    store: FilesystemMemoryStore,
    path: Path,
    *,
    user_id: str,
    entity_id: str,
) -> None:
    store.write_document(
        path,
        front_matter={
            "schema_version": 1,
            "memory_type": "entity",
            "id": entity_id,
            "user_id": user_id,
            "label": entity_id,
            "entity_type": "object",
            "created_at": "2026-06-30T00:00:00+00:00",
            "updated_at": "2026-06-30T00:00:00+00:00",
        },
        body=f"# {entity_id}",
    )


def _record(
    store: FilesystemMemoryStore,
    path: Path,
    *,
    user_id: str,
    memory_type: str,
    source_id: str,
) -> MemoryIndexRecord:
    return _raw_record(
        source_path=path.relative_to(store.root).as_posix(),
        user_id=user_id,
        memory_type=memory_type,
        source_id=source_id,
    )


def _raw_record(
    *,
    source_path: str,
    user_id: str,
    memory_type: str,
    source_id: str,
) -> MemoryIndexRecord:
    return MemoryIndexRecord(
        source_path=source_path,
        source_id=source_id,
        user_id=user_id,
        memory_type=memory_type,
        title=None,
        content_hash="a" * 64,
        indexed_text=source_id,
        tags_json="[]",
        status=None,
        timeline_type=None,
        occurred_at=None,
        updated_at="2026-06-30T00:00:00+00:00",
        importance=0.5,
        confidence=1.0,
        decay_score=1.0,
        embedding=[],
    )
