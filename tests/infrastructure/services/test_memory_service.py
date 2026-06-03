"""Tests for the filesystem memory service adapter."""

from pathlib import Path

import pytest
from flow_res import is_err

from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
)
from app.infrastructure.memory.markdown import (
    MemoryMarkdownError,
    parse_memory_markdown,
    render_memory_markdown,
)
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    encode_path_segment,
)
from app.infrastructure.queries.memory_index_query_service import (
    FilesystemMemoryIndex,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.services.memory_write_service import (
    FilesystemMemoryWriteService,
)
from tests._agent_profile_fixture import copy_agent_profile_bundle


@pytest.mark.anyio
async def test_filesystem_memory_service_retrieve_returns_app_context_pack(
    tmp_path: Path,
) -> None:
    """The adapter should return the app-level memory DTO."""
    copy_agent_profile_bundle(tmp_path / "memory")
    service = FilesystemMemoryService(tmp_path / "memory")
    result = await service.retrieve("hello", "u1")

    assert not is_err(result)
    pack = result.value
    assert isinstance(pack, MemoryContextPack)
    assert pack.user_id == "u1"
    assert pack.profile is not None
    assert pack.profile.display_name == "白鷺 レイナ"
    assert pack.timelines == []
    assert pack.entities == []
    assert pack.context_frame is not None
    assert pack.assembled_context == pack.context_frame.assembled_context
    assert "## Source: profiles/agent/SOUL.md" in (pack.assembled_context or "")

    profile_dir = tmp_path / "memory" / "profiles" / "agent"
    assert (profile_dir / "AGENTS.md").exists()
    assert (profile_dir / "SOUL.md").exists()
    assert (profile_dir / "PERSONAL.md").exists()
    assert (profile_dir / "MEMORY.md").exists()


@pytest.mark.anyio
async def test_filesystem_memory_service_writes_profile_and_entities(
    tmp_path: Path,
) -> None:
    """Profile and entity memories should persist as Markdown files."""
    write_service = FilesystemMemoryWriteService(tmp_path / "memory")

    write_service.write_profile(
        MemoryProfile(
            user_id="u1",
            display_name="ユーザーA",
            summary="落ち着いて記録を残す。",
            traits=["丁寧"],
            preferences=["静かな場所"],
        )
    )
    write_service.write_entity(
        MemoryEntity(
            id="ENT-001",
            user_id="u1",
            label="机",
            entity_type="object",
            status="active",
            aliases=["desk"],
            attributes={"color": "gray"},
            confidence=0.9,
        )
    )
    service = FilesystemMemoryService(tmp_path / "memory")

    result = await service.retrieve("profile", "u1")

    assert not is_err(result)
    assert result.value.profile is not None
    assert result.value.profile.display_name == "ユーザーA"
    assert result.value.entities[0].label == "机"
    assert result.value.search_hits
    assert result.value.timelines == []

    user_profile_file = tmp_path / "memory" / "profiles" / "users" / "u1.md"
    entity_file = tmp_path / "memory" / "entities" / "u1" / "ENT-001.md"
    assert user_profile_file.read_text(encoding="utf-8").startswith("---\n")
    assert entity_file.read_text(encoding="utf-8").startswith("---\n")
    user_doc = parse_memory_markdown(user_profile_file.read_text(encoding="utf-8"))
    assert user_doc.front_matter["profile_scope"] == "user"
    assert "summary" in user_doc.front_matter
    assert "traits" in user_doc.front_matter
    assert "preferences" in user_doc.front_matter
    assert "memory_type: entity" in entity_file.read_text(encoding="utf-8")
    assert "机" in entity_file.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_filesystem_memory_service_preserves_entity_properties(
    tmp_path: Path,
) -> None:
    """Entity DTO conversion should keep properties and missing attributes."""
    service = FilesystemMemoryService(tmp_path / "memory")
    entity_file = tmp_path / "memory" / "entities" / "u1" / "project-x.md"
    entity_file.parent.mkdir(parents=True, exist_ok=True)
    entity_file.write_text(
        render_memory_markdown(
            {
                "schema_version": 1,
                "memory_type": "entity",
                "id": "project-x",
                "user_id": "u1",
                "label": "Project X",
                "entity_type": "project",
                "status": "unresolved",
                "aliases": ["PX"],
                "properties": {
                    "language": "Python",
                    "ports": ["ai_service", "memory_service"],
                    "nullable": None,
                },
                "attributes": {"legacy": "kept"},
                "missing_attributes": ["repository"],
                "created_at": "2026-05-18T00:00:00+00:00",
                "updated_at": "2026-05-18T00:00:00+00:00",
            },
            "# Project X\n\nMemory service project.",
        ),
        encoding="utf-8",
    )

    result = await service.retrieve("Project X repository", "u1")

    assert not is_err(result)
    entity = result.value.entities[0]
    assert entity.properties == {
        "language": "Python",
        "ports": ["ai_service", "memory_service"],
        "nullable": None,
    }
    assert entity.attributes == {"legacy": "kept"}
    assert entity.missing_attributes == ["repository"]
    assert result.value.search_hits[0].source.id == "project-x"
    assert "missing_attributes: repository" in (result.value.assembled_context or "")


@pytest.mark.anyio
async def test_filesystem_memory_service_writes_timeline_markdown(
    tmp_path: Path,
) -> None:
    """Chat logs should persist as timeline Markdown files."""
    write_service = FilesystemMemoryWriteService(tmp_path / "memory")

    await write_service.add_log(
        user_id="u1",
        role="user",
        content="remember this",
        metadata={"chat_type": "DISCORD"},
    )
    service = FilesystemMemoryService(tmp_path / "memory")

    result = await service.retrieve("remember", "u1")

    assert not is_err(result)
    assert len(result.value.timelines) == 1
    assert result.value.timelines[0].content == "remember this"

    files = sorted((tmp_path / "memory" / "timeline" / "u1" / "raw").rglob("*.md"))
    assert len(files) == 1
    timeline_text = files[0].read_text(encoding="utf-8")
    assert timeline_text.startswith("---\n")
    assert "schema_version: 1" in timeline_text
    assert "memory_type: timeline" in timeline_text
    assert "timeline_type: raw" in timeline_text


def test_memory_markdown_round_trips_unicode_front_matter() -> None:
    """Markdown parser should preserve Unicode and validate required fields."""
    markdown = render_memory_markdown(
        {
            "schema_version": 1,
            "memory_type": "entity",
            "id": "ENT-001",
            "user_id": "u1",
            "label": "机",
            "entity_type": "object",
            "created_at": "2026-05-18T00:00:00+00:00",
            "updated_at": "2026-05-18T00:00:00+00:00",
        },
        "# 机\n\n日本語の本文",
    )

    document = parse_memory_markdown(markdown)

    assert document.front_matter["schema_version"] == 1
    assert document.front_matter["memory_type"] == "entity"
    assert document.front_matter["label"] == "机"
    assert "日本語の本文" in document.body


def test_memory_markdown_rejects_missing_required_fields() -> None:
    """Malformed front matter should fail before service DTO conversion."""
    markdown = "---\nschema_version: 1\nmemory_type: timeline\n---\n\nbody\n"

    with pytest.raises(MemoryMarkdownError, match="missing required fields"):
        parse_memory_markdown(markdown)


def test_memory_store_uses_safe_user_scoped_paths(tmp_path: Path) -> None:
    """Path generation should scope user data and encode unsafe ID characters."""
    store = FilesystemMemoryStore(tmp_path / "memory")

    entity_path = store.entity_path("discord:123", "entity/abc")
    user_profile_path = store.user_profile_path("discord:123")

    assert encode_path_segment("discord:123") == "discord%3A123"
    assert entity_path == (
        tmp_path / "memory" / "entities" / "discord%3A123" / "entity%2Fabc.md"
    )
    assert user_profile_path == (
        tmp_path / "memory" / "profiles" / "users" / "discord%3A123.md"
    )


@pytest.mark.anyio
async def test_filesystem_memory_service_returns_err_for_malformed_user_file(
    tmp_path: Path,
) -> None:
    """Malformed selected user-scoped files should become MemoryServiceError."""
    service = FilesystemMemoryService(tmp_path / "memory")
    malformed_file = (
        tmp_path / "memory" / "timeline" / "u1" / "raw" / "2026" / "05" / "bad.md"
    )
    malformed_file.parent.mkdir(parents=True, exist_ok=True)
    malformed_file.write_text("not front matter\n", encoding="utf-8")

    result = await service.retrieve("hello", "u1")

    assert is_err(result)
    assert "missing YAML front matter" in str(result.error)


@pytest.mark.anyio
async def test_filesystem_memory_service_rejects_path_scope_mismatch(
    tmp_path: Path,
) -> None:
    """A file under one user scope must not claim another front matter user_id."""
    service = FilesystemMemoryService(tmp_path / "memory")
    mismatched_file = tmp_path / "memory" / "entities" / "u1" / "ENT-001.md"
    mismatched_file.parent.mkdir(parents=True, exist_ok=True)
    mismatched_file.write_text(
        render_memory_markdown(
            {
                "schema_version": 1,
                "memory_type": "entity",
                "id": "ENT-001",
                "user_id": "u2",
                "label": "desk",
                "entity_type": "object",
                "created_at": "2026-05-18T00:00:00+00:00",
                "updated_at": "2026-05-18T00:00:00+00:00",
            },
            "# desk",
        ),
        encoding="utf-8",
    )

    result = await service.retrieve("desk", "u1")

    assert is_err(result)
    assert "path scope and front matter user_id disagree" in str(result.error)


@pytest.mark.anyio
async def test_filesystem_memory_service_prefers_memory_root_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEMORY_ROOT should control where the agent bundle is read from."""
    preferred_root = tmp_path / "preferred"
    monkeypatch.setenv("MEMORY_ROOT", str(preferred_root))

    copy_agent_profile_bundle(preferred_root)
    service = FilesystemMemoryService()
    result = await service.retrieve("hello", "u1")

    assert not is_err(result)
    assert (preferred_root / "profiles" / "agent" / "SOUL.md").exists()
    assert (preferred_root / "profiles" / "agent" / "AGENTS.md").exists()
    agents_text = (preferred_root / "profiles" / "agent" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert "communication_style:" not in agents_text
    assert "known_constraints:" not in agents_text
    assert "Do not mention that you are an AI" in agents_text
    assert "Treat conversation like hosting a guest" in agents_text
    assert "Relational habits" in agents_text
    assert "at most one easy-to-answer question" in agents_text


@pytest.mark.anyio
async def test_filesystem_memory_service_accepts_concrete_index(
    tmp_path: Path,
) -> None:
    """The service should accept the concrete filesystem index implementation."""
    copy_agent_profile_bundle(tmp_path / "memory")
    service = FilesystemMemoryService(
        tmp_path / "memory",
        index=FilesystemMemoryIndex(),
    )

    result = await service.retrieve("hello", "u1")

    assert not is_err(result)
    assert result.value.profile is not None
