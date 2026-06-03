"""Tests for prompt-ready memory context assembly."""

from pathlib import Path

from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
)
from app.infrastructure.memory.context_assembler import (
    assemble_context_frame,
)
from app.infrastructure.memory.markdown import (
    parse_memory_markdown,
    render_memory_markdown,
)
from app.infrastructure.queries.memory_index_query_service import (
    FilesystemMemoryIndex,
)


def test_assemble_context_frame_orders_sections_with_source_headers() -> None:
    """Assembler should emit Primary, Functional, then Peripheral sections."""
    results = FilesystemMemoryIndex().search_memory_index(
        "desk concise summary",
        [
            _document(
                "entities/u1/desk.md",
                {
                    "memory_type": "entity",
                    "id": "desk",
                    "user_id": "u1",
                    "label": "Desk",
                    "entity_type": "object",
                    "properties": {"color": "gray"},
                },
                "# Desk\n\nThe desk is gray.",
            ),
            _document(
                "profiles/agent/AGENTS.md",
                {
                    "memory_type": "profile",
                    "id": "agent",
                    "profile_scope": "agent",
                    "user_id": None,
                    "profile_part": "AGENTS",
                    "display_name": "Agent",
                    "pinned": True,
                },
                "\n".join(
                    [
                        "# Agent",
                        "",
                        "## Persona Contract",
                        "",
                        "Use concise answers.",
                        "",
                        "## Communication Style",
                        "",
                        "- Japanese",
                        "- direct answers",
                        "",
                        "## Known Constraints",
                        "",
                        "- Do not mention being AI",
                    ]
                ),
            ),
            _document(
                "profiles/agent/SOUL.md",
                {
                    "memory_type": "profile",
                    "id": "agent",
                    "profile_scope": "agent",
                    "user_id": None,
                    "profile_part": "SOUL",
                    "display_name": "Agent",
                    "pinned": True,
                },
                "\n".join(
                    [
                        "# Agent",
                        "",
                        "## Summary",
                        "",
                        "Use concise answers.",
                        "",
                        "## Traits",
                        "",
                        "- calm",
                    ]
                ),
            ),
            _document(
                "profiles/agent/PERSONAL.md",
                {
                    "memory_type": "profile",
                    "id": "agent",
                    "profile_scope": "agent",
                    "user_id": None,
                    "profile_part": "PERSONAL",
                    "display_name": "Agent",
                    "pinned": True,
                },
                "\n".join(
                    [
                        "# Agent",
                        "",
                        "## Preferences",
                        "",
                        "- tea",
                    ]
                ),
            ),
            _document(
                "profiles/agent/MEMORY.md",
                {
                    "memory_type": "profile",
                    "id": "agent",
                    "profile_scope": "agent",
                    "user_id": None,
                    "profile_part": "MEMORY",
                    "display_name": "Agent",
                    "pinned": True,
                },
                "\n".join(
                    [
                        "# Agent",
                        "",
                        "## Stable notes",
                        "",
                        "- Use concise answers.",
                    ]
                ),
            ),
            _document(
                "timeline/u1/daily/2026/05/2026-05-18.md",
                {
                    "memory_type": "timeline",
                    "id": "daily",
                    "user_id": "u1",
                    "timeline_type": "raw",
                    "kind": "user",
                    "content": "User mentioned a desk in a summary.",
                    "occurred_at": "2026-05-18T00:00:00+00:00",
                    "source": "chat",
                },
                "# Raw\n\nUser mentioned a desk.",
            ),
        ],
        MemorySearchFilters(user_id="u1"),
    )

    frame = assemble_context_frame(results)

    assert [section.name for section in frame.sections] == [
        "primary",
        "functional",
        "peripheral",
    ]
    assert "# Primary" in frame.assembled_context
    assert "# Functional" in frame.assembled_context
    assert "# Peripheral" in frame.assembled_context
    assert "## Source: entities/u1/desk.md" in frame.assembled_context
    assert "## Source: profiles/agent/AGENTS.md" in frame.assembled_context
    assert "## Source: profiles/agent/SOUL.md" in frame.assembled_context
    assert "## Source: profiles/agent/PERSONAL.md" in frame.assembled_context
    assert "## Source: profiles/agent/MEMORY.md" in frame.assembled_context
    assert "profile_part: AGENTS" in frame.assembled_context
    assert "profile_part: SOUL" in frame.assembled_context
    assert "## Communication Style" in frame.assembled_context
    assert "Japanese" in frame.assembled_context
    assert "direct answers" in frame.assembled_context
    assert "## Known Constraints" in frame.assembled_context
    assert "Do not mention being AI" in frame.assembled_context


def test_assemble_context_frame_drops_peripheral_entries_under_budget() -> None:
    """Peripheral context should be omitted before primary context."""
    results = FilesystemMemoryIndex().search_memory_index(
        "desk verbose",
        [
            _document(
                "entities/u1/desk.md",
                {
                    "memory_type": "entity",
                    "id": "desk",
                    "user_id": "u1",
                    "label": "Desk",
                    "entity_type": "object",
                },
                "# Desk\n\nImportant desk facts.",
            ),
            _document(
                "timeline/u1/raw/2026/05/verbose.md",
                {
                    "memory_type": "timeline",
                    "id": "verbose",
                    "user_id": "u1",
                    "timeline_type": "raw",
                    "kind": "user",
                    "content": "verbose " * 80,
                    "occurred_at": "2026-05-18T00:00:00+00:00",
                    "source": "chat",
                },
                "# Verbose\n\n" + ("verbose " * 80),
            ),
        ],
        MemorySearchFilters(user_id="u1"),
    )

    frame = assemble_context_frame(results, max_chars=360)

    assert "## Source: entities/u1/desk.md" in frame.assembled_context
    assert "## Source: timeline/u1/raw/2026/05/verbose.md" not in (
        frame.assembled_context
    )


def test_assemble_context_frame_treats_relationship_entity_as_functional() -> None:
    """Relationship memory should guide behavior rather than become the answer."""
    results = FilesystemMemoryIndex().search_memory_index(
        "relationship shirasagi reina",
        [
            _document(
                "entities/u1/relationship%3Ashirasagi-reina.md",
                {
                    "memory_type": "entity",
                    "id": "relationship:shirasagi-reina",
                    "user_id": "u1",
                    "label": "白鷺レイナとの関係",
                    "entity_type": "relationship",
                    "properties": {
                        "stage": 1,
                        "stage_name": "顔なじみ",
                        "trust_score": 12,
                        "warmth_score": 8,
                    },
                    "tags": ["relationship", "agent-growth"],
                },
                "# 白鷺レイナとの関係",
            )
        ],
        MemorySearchFilters(user_id="u1"),
    )

    frame = assemble_context_frame(results)

    assert [section.name for section in frame.sections] == ["functional"]
    assert "# Functional" in frame.assembled_context
    assert "entity_type: relationship" in frame.assembled_context
    assert "stage_name: 顔なじみ" in frame.assembled_context


def _document(
    reference: str,
    front_matter: dict[str, object],
    body: str,
) -> MemoryIndexDocument:
    full_front_matter: dict[str, object] = {
        "schema_version": 1,
        "created_at": "2026-05-18T00:00:00+00:00",
        "updated_at": "2026-05-18T00:00:00+00:00",
        "tags": [],
        "importance": 0.7,
        "confidence": 0.9,
        "metadata": {},
        **front_matter,
    }
    return MemoryIndexDocument(
        path=Path(reference),
        reference=reference,
        document=parse_memory_markdown(render_memory_markdown(full_front_matter, body)),
    )
