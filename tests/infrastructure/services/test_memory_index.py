"""Tests for the dependency-free memory keyword index."""

import sqlite3
from pathlib import Path

from flow_res import is_err

from app.contracts.messages.memory_context import MemoryEntity
from app.infrastructure.services.memory_index import (
    FilesystemMemoryIndex,
    MemoryIndexDocument,
    MemorySearchFilters,
    search_memory_index,
)
from app.infrastructure.services.memory_markdown import (
    parse_memory_markdown,
    render_memory_markdown,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService


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

    hits = search_memory_index(
        "workbench gray",
        documents,
        MemorySearchFilters(user_id="u1", tags=("office",)),
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

    timeline_hits = search_memory_index(
        "memory index",
        documents,
        MemorySearchFilters(
            user_id="u1",
            memory_type="timeline",
            timeline_type="daily_summary",
            date_from="2026-05-01T00:00:00+00:00",
        ),
    )
    unresolved_hits = search_memory_index(
        "unknown repository",
        documents,
        MemorySearchFilters(user_id="u1", unresolved=True),
    )
    archived_hits = search_memory_index(
        "archived",
        documents,
        MemorySearchFilters(user_id="u1"),
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
    )
    function_hits = search_memory_index(
        "workbench gray",
        documents,
        MemorySearchFilters(user_id="u1", tags=("office",)),
    )

    assert [hit.hit.source.id for hit in wrapped_hits] == [
        hit.hit.source.id for hit in function_hits
    ]


def test_filesystem_memory_index_rebuilds_and_repairs_snapshot(
    tmp_path: Path,
) -> None:
    """The adapter should persist and repair a local index snapshot."""
    memory_root = tmp_path / "memory"
    service = FilesystemMemoryService(memory_root)
    service.write_entity(
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

    index = FilesystemMemoryIndex(root=memory_root)
    rebuild_result = index.rebuild_memory_index(user_id="u1")

    assert not is_err(rebuild_result)
    assert rebuild_result.value >= 2

    db_path = memory_root / "index" / "memory_index.sqlite3"
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            select source_path, source_id, content_hash, indexed_text, tags_json
            from memory_index_documents
            where source_id = ?
            """,
            ("desk-1",),
        ).fetchone()
        row_count = connection.execute(
            "select count(*) from memory_index_documents where user_id = ?",
            ("u1",),
        ).fetchone()

    assert row is not None
    assert row_count is not None
    assert row_count[0] >= 1
    assert row[0] == "entities/u1/desk-1.md"
    assert row[1] == "desk-1"
    assert len(row[2]) == 64
    assert "Standing Desk" in row[3]
    assert "workbench" in row[3]
    assert row[4] == "[]"

    hits = index.search_memory_index(
        "standing desk",
        [],
        MemorySearchFilters(user_id="u1"),
    )
    assert hits
    assert hits[0].hit.source.id == "desk-1"

    entity_path = memory_root / "entities" / "u1" / "desk-1.md"
    entity_path.unlink()

    repair_result = index.repair_memory_index(user_id="u1")

    assert not is_err(repair_result)
    assert repair_result.value >= 1

    with sqlite3.connect(db_path) as connection:
        repaired_row = connection.execute(
            """
            select count(*) from memory_index_documents
            where source_id = ?
            """,
            ("desk-1",),
        ).fetchone()

    assert repaired_row is not None
    assert repaired_row[0] == 0

    repaired_hits = index.search_memory_index(
        "standing desk",
        [],
        MemorySearchFilters(user_id="u1"),
    )
    assert all(hit.hit.source.id != "desk-1" for hit in repaired_hits)


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
    return MemoryIndexDocument(
        path=Path(reference),
        reference=reference,
        document=parse_memory_markdown(render_memory_markdown(full_front_matter, body)),
    )
