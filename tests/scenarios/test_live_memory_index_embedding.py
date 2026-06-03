"""Live scenario tests for memory index retrieval."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from flow_res import is_err

from app.contracts.messages.memory_index import MemorySearchFilters
from app.infrastructure import database
from app.infrastructure.memory.embedding import GeminiEmbeddingService
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.queries.memory_index_query_service import (
    FilesystemMemoryIndex,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService
from scripts.memory_index_embedding import _rebuild_index_projection

pytestmark = pytest.mark.scenario


@pytest.mark.anyio
async def test_live_gemini_embeddings_rank_matching_timeline_document(
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

    index_db = tmp_path / "memory_index.sqlite3"
    await _rebuild_index_projection(
        memory_root=memory_root,
        index_db=index_db,
        user_id="u1",
        embedding_service=embedding_service,
    )
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'scenario.sqlite3'}")

    query = "お風呂から上がったあとに東京バナナの話をした"
    embedded = await embedding_service.embed_texts([query])
    assert not is_err(embedded)
    query_embedding = embedded.value[0]
    hits = FilesystemMemoryIndex(root=memory_root).search_memory_index(
        query,
        [],
        MemorySearchFilters(user_id="u1"),
        index_db_path=index_db,
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

    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'scenario.sqlite3'}")
    service = FilesystemMemoryService(
        root=memory_root,
        embedding_service=embedding_service,
    )

    result = await service.retrieve(
        "お風呂から上がったあとに東京バナナの話をした",
        "u1",
    )

    assert not is_err(result)
    assert result.value.search_hits
    top_hit = result.value.search_hits[0]
    reference = top_hit.source.reference
    assert reference is not None
    assert "2026-05-18" in reference
    assert reference.endswith("bath-time-chat.md")
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
