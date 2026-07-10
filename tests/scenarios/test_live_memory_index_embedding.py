"""Live scenario tests for memory index retrieval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from flow_res import is_err
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.memory_index import MemorySearchFilters
from app.infrastructure.memory.embedding import GeminiEmbeddingService
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.queries.memory_index_projection_query import (
    SQLAlchemyMemoryIndexQuery,
)
from app.infrastructure.queries.memory_index_query_service import (
    MemoryIndexSearch,
)
from app.infrastructure.services.memory_index_maintenance import (
    MemoryIndexMaintenanceService,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService
from tests._agent_profile_fixture import _character_id

pytestmark = pytest.mark.scenario


@pytest.mark.anyio
async def test_live_gemini_embeddings_rank_matching_timeline_document(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Live Gemini embeddings should rank the matching document first."""

    embedding_service = _build_live_embedding_service()
    if embedding_service is None:
        pytest.skip("GEMINI_API_KEY is required for live embedding scenario tests.")

    memory_root = tmp_path / "memory"
    store = FilesystemMemoryStore(memory_root)
    _write_timeline_summary(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        section_slug="bath-time-chat",
        title="お風呂前のひと息",
        body_lines=[
            "お風呂に入る前に東京バナナを食べる話をした。",
            "荷物の準備も先に進める流れになった。",
        ],
    )
    _write_timeline_summary(
        store,
        user_id="u1",
        day=date(2026, 5, 17),
        section_slug="work-progress",
        title="作業の整理",
        body_lines=[
            "仕事の段取りと翌日の確認を進めた。",
            "お風呂やお菓子とは関係のない内容。",
        ],
    )

    character_id = _character_id()
    maintenance = MemoryIndexMaintenanceService(
        root=memory_root,
        session_factory=session_factory,
        embedding_service=embedding_service,
        character_id=character_id,
    )
    rebuild_result = await maintenance.rebuild_memory_index(user_id="u1")
    assert not is_err(rebuild_result)
    projection_query = SQLAlchemyMemoryIndexQuery(session_factory, store)
    documents_result = await projection_query.list_documents(
        user_id="u1",
        character_id=character_id,
        relationship_entity_id=f"relationship:{character_id}",
    )
    assert not is_err(documents_result)

    query = "お風呂から上がったあとに東京バナナの話をした"
    embedded = await embedding_service.embed_texts([query])
    assert not is_err(embedded)
    query_embedding = embedded.value[0]
    hits = MemoryIndexSearch(embedding_service).search_memory_index(
        query,
        documents_result.value,
        MemorySearchFilters(user_id="u1"),
        query_embedding=query_embedding,
        limit=3,
    )

    assert hits
    top_hit = hits[0]
    reference = top_hit.hit.source.reference
    assert reference is not None
    assert reference.endswith("bath-time-chat.md")
    assert reference.startswith("timeline/u1/sections/2026/05/")
    assert top_hit.hit.score > 0.55


@pytest.mark.anyio
async def test_live_gemini_memory_service_returns_same_day_hit(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """Live Gemini retrieval should prefer the matching day entry."""

    embedding_service = _build_live_embedding_service()
    if embedding_service is None:
        pytest.skip("GEMINI_API_KEY is required for live embedding scenario tests.")

    memory_root = tmp_path / "memory"
    store = FilesystemMemoryStore(memory_root)
    _write_timeline_summary(
        store,
        user_id="u1",
        day=date(2026, 5, 18),
        section_slug="bath-time-chat",
        title="お風呂前のひと息",
        body_lines=[
            "お風呂に入る前に東京バナナを食べる話をした。",
            "荷物の準備も先に進める流れになった。",
        ],
    )
    _write_timeline_summary(
        store,
        user_id="u1",
        day=date(2026, 5, 17),
        section_slug="work-progress",
        title="作業の整理",
        body_lines=[
            "仕事の段取りと翌日の確認を進めた。",
            "お風呂やお菓子とは関係のない内容。",
        ],
    )

    character_id = _character_id()
    maintenance = MemoryIndexMaintenanceService(
        root=memory_root,
        session_factory=session_factory,
        embedding_service=embedding_service,
        character_id=character_id,
    )
    rebuild_result = await maintenance.rebuild_memory_index(user_id="u1")
    assert not is_err(rebuild_result)
    projection_query = SQLAlchemyMemoryIndexQuery(session_factory, store)
    service = FilesystemMemoryService(
        index_query=projection_query,
        character_id=character_id,
    )

    result = await service.build_context("u1")

    assert not is_err(result)
    assert result.value.manifest_items
    assert "timeline:" in result.value.manifest_items[0].memory_id
    assert "東京バナナ" in (result.value.assembled_context or "")


def _build_live_embedding_service() -> GeminiEmbeddingService | None:
    service = GeminiEmbeddingService(output_dimensionality=128)
    if service._client is None:
        return None
    return service


def _write_timeline_summary(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
    day: date,
    section_slug: str,
    title: str,
    body_lines: list[str],
) -> None:
    body = "\n".join(["# " + title, "", *body_lines])
    store.write_document(
        store.section_timeline_path(
            user_id=user_id,
            day=day,
            section_slug=section_slug,
        ),
        front_matter={
            "schema_version": 1,
            "memory_type": "timeline",
            "id": f"{user_id}-{day.isoformat()}-{section_slug}",
            "user_id": user_id,
            "timeline_type": "section_summary",
            "kind": "summary",
            "content": "\n".join(body_lines),
            "occurred_at": f"{day.isoformat()}T00:00:00+00:00",
            "source": "consolidation",
            "entity_ids": [],
            "summary_of": [],
            "section_slug": section_slug,
            "section_title": title,
            "consolidation_state": "complete",
            "retention_state": "active",
            "last_accessed_at": None,
            "access_count": 0,
            "decay_score": 1.0,
            "created_at": "2026-05-17T00:00:00+00:00",
            "updated_at": "2026-05-17T00:00:00+00:00",
            "tags": [],
            "importance": 0.6,
            "confidence": 1.0,
            "pinned": False,
            "metadata": {},
            "source_chat_ids": [],
            "extraction_confidence": 1.0,
        },
        body=body,
    )
