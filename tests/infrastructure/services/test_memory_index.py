"""Tests for the dependency-free memory keyword index."""

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from flow_res import is_err
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_context import MemoryEntity
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
)
from app.infrastructure.memory.embedding import embed_text_deterministically
from app.infrastructure.memory.markdown import (
    parse_memory_markdown,
    render_memory_markdown,
)
from app.infrastructure.orm_models.memory_index_orm import MemoryIndexDocumentORM
from app.infrastructure.queries.memory_index_query_service import (
    FilesystemMemoryIndex,
)
from app.infrastructure.services.memory_index_maintenance import (
    MemoryIndexMaintenanceService,
)
from app.infrastructure.services.memory_write_service import (
    FilesystemMemoryWriteService,
)
from tests._agent_profile_fixture import _character_id

_memory_index_source_id = cast(Any, MemoryIndexDocumentORM.source_id)
_memory_index_user_id = cast(Any, MemoryIndexDocumentORM.user_id)


def test_search_memory_index_ranks_entity_alias_and_separates_users() -> None:
    """Entity aliases should be searchable without leaking other user data."""
    documents = [
        _document(
            "entities/u1/desk.md",
            {
                "memory_type": "entity",
                "id": "desk",
                "user_id": "u1",
                "label": "Standing Desk",
                "entity_type": "object",
                "aliases": ["workbench"],
                "properties": {"color": "gray"},
                "tags": ["office"],
            },
            "# Standing Desk\n\nGray workbench for coding.",
        ),
        _document(
            "entities/u2/desk.md",
            {
                "memory_type": "entity",
                "id": "desk-other",
                "user_id": "u2",
                "label": "Standing Desk",
                "entity_type": "object",
                "aliases": ["workbench"],
                "properties": {"color": "black"},
                "tags": ["office"],
            },
            "# Standing Desk\n\nOther user's desk.",
        ),
    ]

    hits = FilesystemMemoryIndex().search_memory_index(
        "workbench gray",
        documents,
        MemorySearchFilters(user_id="u1", tags=("office",)),
        character_id=_character_id(),
    )

    assert [hit.hit.source.id for hit in hits] == ["desk"]
    assert hits[0].hit.source.user_id == "u1"
    assert "workbench" in hits[0].hit.matched_terms
    assert "gray" in hits[0].hit.matched_terms


def test_search_memory_index_filters_timeline_date_status_and_archived() -> None:
    """Search filters should cover dates, timeline type, status, and retention."""
    documents = [
        _document(
            "timeline/u1/daily/2026/05/2026-05-17.md",
            {
                "memory_type": "timeline",
                "id": "daily-1",
                "user_id": "u1",
                "timeline_type": "daily_summary",
                "kind": "summary",
                "content": "Discussed the memory index plan.",
                "occurred_at": "2026-05-17T00:00:00+00:00",
                "source": "consolidation",
                "retention_state": "active",
                "tags": ["memory"],
            },
            "# Daily summary",
        ),
        _document(
            "timeline/u1/raw/2026/04/2026-04-10_user-old.md",
            {
                "memory_type": "timeline",
                "id": "raw-old",
                "user_id": "u1",
                "timeline_type": "raw",
                "kind": "user",
                "content": "Discussed the memory index plan.",
                "occurred_at": "2026-04-10T00:00:00+00:00",
                "source": "chat",
                "retention_state": "active",
            },
            "# Raw",
        ),
        _document(
            "entities/u1/unknown.md",
            {
                "memory_type": "entity",
                "id": "unknown-project",
                "user_id": "u1",
                "label": "Unknown Project",
                "entity_type": "project",
                "status": "unresolved",
                "missing_attributes": ["repository"],
            },
            "# Unknown Project",
        ),
        _document(
            "entities/u1/archived.md",
            {
                "memory_type": "entity",
                "id": "archived-project",
                "user_id": "u1",
                "label": "Archived Project",
                "entity_type": "project",
                "status": "active",
                "retention_state": "archived",
            },
            "# Archived Project\n\nmemory index plan",
        ),
    ]

    timeline_hits = FilesystemMemoryIndex().search_memory_index(
        "memory index",
        documents,
        MemorySearchFilters(
            user_id="u1",
            memory_type="timeline",
            timeline_type="daily_summary",
            date_from="2026-05-01T00:00:00+00:00",
        ),
        character_id=_character_id(),
    )
    unresolved_hits = FilesystemMemoryIndex().search_memory_index(
        "unknown repository",
        documents,
        MemorySearchFilters(user_id="u1", unresolved=True),
        character_id=_character_id(),
    )
    archived_hits = FilesystemMemoryIndex().search_memory_index(
        "archived",
        documents,
        MemorySearchFilters(user_id="u1"),
        character_id=_character_id(),
    )

    assert [hit.hit.source.id for hit in timeline_hits] == ["daily-1"]
    assert [hit.hit.source.id for hit in unresolved_hits] == ["unknown-project"]
    assert all(hit.hit.source.id != "archived-project" for hit in archived_hits)


def test_filesystem_memory_index_wraps_search_function() -> None:
    """The concrete filesystem index should delegate to the search function."""
    documents = [
        _document(
            "entities/u1/desk.md",
            {
                "memory_type": "entity",
                "id": "desk",
                "user_id": "u1",
                "label": "Standing Desk",
                "entity_type": "object",
                "aliases": ["workbench"],
                "properties": {"color": "gray"},
                "tags": ["office"],
            },
            "# Standing Desk\n\nGray workbench for coding.",
        )
    ]

    index = FilesystemMemoryIndex()
    wrapped_hits = index.search_memory_index(
        "workbench gray",
        documents,
        MemorySearchFilters(user_id="u1", tags=("office",)),
        character_id=_character_id(),
    )
    assert [hit.hit.source.id for hit in wrapped_hits] == ["desk"]


@pytest.mark.anyio
async def test_memory_index_maintenance_rebuilds_and_repairs_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """The adapter should persist and repair a local index snapshot."""
    memory_root = tmp_path / "memory"
    write_service = FilesystemMemoryWriteService(memory_root)
    write_service.write_entity(
        MemoryEntity(
            id="desk-1",
            user_id="u1",
            label="Standing Desk",
            entity_type="object",
            status="active",
            aliases=["workbench"],
            attributes={"color": "gray"},
            confidence=0.9,
        )
    )

    maintenance = MemoryIndexMaintenanceService(
        root=memory_root,
        session_factory=session_factory,
        character_id=_character_id(),
    )
    rebuild_result = await maintenance.rebuild_memory_index(user_id="u1")

    assert not is_err(rebuild_result)
    assert rebuild_result.value >= 1

    async with session_factory() as session:
        row = await session.execute(
            select(MemoryIndexDocumentORM).where(_memory_index_source_id == "desk-1")
        )
        rows = await session.execute(
            select(MemoryIndexDocumentORM).where(_memory_index_user_id == "u1")
        )

    orm_row = row.scalars().first()
    user_rows = rows.scalars().all()
    assert orm_row is not None
    assert len(user_rows) >= 1
    assert orm_row.source_path == "entities/u1/desk-1.md"
    assert orm_row.source_id == "desk-1"
    assert len(orm_row.content_hash) == 64
    assert "Standing Desk" in orm_row.indexed_text
    assert "workbench" in orm_row.indexed_text
    assert orm_row.tags_json == "[]"
    assert len(orm_row.embedding) > 0

    index = FilesystemMemoryIndex(root=memory_root)
    hits = index.search_memory_index(
        "standing desk",
        [],
        MemorySearchFilters(user_id="u1"),
        character_id=_character_id(),
    )
    assert hits
    assert hits[0].hit.source.id == "desk-1"

    entity_path = memory_root / "entities" / "u1" / "desk-1.md"
    entity_path.unlink()

    repair_result = await maintenance.repair_memory_index(user_id="u1")

    assert not is_err(repair_result)

    async with session_factory() as session:
        repaired_row = await session.execute(
            select(MemoryIndexDocumentORM).where(_memory_index_source_id == "desk-1")
        )

    assert repaired_row.scalars().first() is None

    repaired_hits = index.search_memory_index(
        "standing desk",
        [],
        MemorySearchFilters(user_id="u1"),
        character_id=_character_id(),
    )
    assert all(hit.hit.source.id != "desk-1" for hit in repaired_hits)


def test_search_memory_index_uses_persisted_embedding_when_terms_do_not_match(
    tmp_path: Path,
) -> None:
    """Persisted embeddings should drive retrieval even without lexical overlap."""
    index_db_path = tmp_path / "memory_index.sqlite3"
    _create_index_db(index_db_path)
    query = "remember the constellation"
    query_embedding = embed_text_deterministically(query, dimension=8)
    stored_embedding = list(query_embedding)
    _insert_index_row(
        index_db_path,
        {
            "source_path": "profiles/users/u1.md",
            "user_id": "u1",
            "memory_type": "profile",
            "source_id": "profile-u1",
            "title": None,
            "content_hash": "a" * 64,
            "indexed_text": "",
            "tags_json": "[]",
            "status": None,
            "timeline_type": None,
            "occurred_at": None,
            "updated_at": "2026-05-18T00:00:00+00:00",
            "importance": 0.6,
            "confidence": 1.0,
            "decay_score": 1.0,
            "embedding": stored_embedding,
        },
    )

    documents = [
        _document(
            "profiles/users/u1.md",
            {
                "memory_type": "profile",
                "id": "profile-u1",
                "user_id": "u1",
                "display_name": None,
                "summary": "",
                "traits": [],
                "preferences": [],
                "tags": [],
            },
            "",
        )
    ]

    hits = FilesystemMemoryIndex().search_memory_index(
        query,
        documents,
        MemorySearchFilters(user_id="u1"),
        character_id=_character_id(),
        index_db_path=index_db_path,
        query_embedding=query_embedding,
    )

    assert [hit.hit.source.id for hit in hits] == ["profile-u1"]
    assert hits[0].rank_score > 0.0


def _document(
    reference: str,
    front_matter: dict[str, object],
    body: str,
) -> MemoryIndexDocument:
    full_front_matter: dict[str, object] = {
        "schema_version": 1,
        "created_at": "2026-05-18T00:00:00+00:00",
        "updated_at": "2026-05-18T00:00:00+00:00",
        "importance": 0.7,
        "confidence": 0.9,
        "pinned": False,
        "metadata": {},
        **front_matter,
    }
    if full_front_matter.get("memory_type") == "profile":
        full_front_matter.setdefault(
            "profile_scope",
            "agent" if full_front_matter.get("user_id") is None else "user",
        )
    return MemoryIndexDocument(
        path=Path(reference),
        reference=reference,
        document=parse_memory_markdown(render_memory_markdown(full_front_matter, body)),
    )


def _create_index_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            create table memory_index_documents (
                source_path text primary key,
                user_id text,
                memory_type text not null,
                source_id text not null,
                title text,
                content_hash text not null,
                indexed_text text not null,
                tags_json text not null,
                status text,
                timeline_type text,
                occurred_at text,
                updated_at text not null,
                importance real not null,
                confidence real not null,
                decay_score real not null,
                embedding json not null
            )
            """
        )
        connection.commit()


def _insert_index_row(path: Path, row: dict[str, object]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            insert into memory_index_documents (
                source_path,
                user_id,
                memory_type,
                source_id,
                title,
                content_hash,
                indexed_text,
                tags_json,
                status,
                timeline_type,
                occurred_at,
                updated_at,
                importance,
                confidence,
                decay_score,
                embedding
            ) values (
                :source_path,
                :user_id,
                :memory_type,
                :source_id,
                :title,
                :content_hash,
                :indexed_text,
                :tags_json,
                :status,
                :timeline_type,
                :occurred_at,
                :updated_at,
                :importance,
                :confidence,
                :decay_score,
                json(:embedding)
            )
            """,
            {**row, "embedding": json.dumps(row["embedding"])},
        )
        connection.commit()
