"""Tests for prompt-ready memory context assembly."""

from pathlib import Path

from app.infrastructure.services.memory_context_assembler import (
    assemble_context_frame,
)
from app.infrastructure.services.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
    search_memory_index,
)
from app.infrastructure.services.memory_markdown import (
    parse_memory_markdown,
    render_memory_markdown,
)


def test_assemble_context_frame_orders_sections_with_source_headers() -> None:
    """Assembler should emit Primary, Functional, then Peripheral sections."""
    results = search_memory_index(
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
                "profiles/agent.md",
                {
                    "memory_type": "profile",
                    "id": "agent",
                    "profile_scope": "agent",
                    "user_id": None,
                    "display_name": "Agent",
                    "summary": "Use concise answers.",
                    "pinned": True,
                },
                "# Agent\n\nUse concise answers.",
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
    assert "## Source: profiles/agent.md" in frame.assembled_context


def test_assemble_context_frame_drops_peripheral_entries_under_budget() -> None:
    """Peripheral context should be omitted before primary context."""
    results = search_memory_index(
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
