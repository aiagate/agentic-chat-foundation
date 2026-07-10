"""Tests for the filesystem memory service adapter."""

from pathlib import Path

import pytest
from flow_res import Ok, Result, is_err

from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
)
from app.contracts.messages.memory_index import MemoryIndexDocument
from app.contracts.ports.memory_index_query import (
    IMemoryIndexQuery,
    MemoryIndexQueryError,
)
from app.infrastructure.memory.context_loader import read_index_documents
from app.infrastructure.memory.markdown import (
    MemoryMarkdownError,
    parse_memory_markdown,
    render_memory_markdown,
)
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    default_memory_root,
    encode_path_segment,
)
from app.infrastructure.services.agent_profile_service import (
    FilesystemAgentProfileService,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.services.memory_write_service import (
    FilesystemMemoryWriteService,
)
from tests._agent_profile_fixture import (
    _character_id,
    copy_agent_profile_bundle,
)


class _FilesystemProjectionQuery(IMemoryIndexQuery):
    """Unit-test query that projects the fixture Markdown documents in memory."""

    def __init__(self, store: FilesystemMemoryStore) -> None:
        self._store = store

    async def list_documents(
        self,
        *,
        user_id: str,
        character_id: str,
        relationship_entity_id: str,
    ) -> Result[list[MemoryIndexDocument], MemoryIndexQueryError]:
        return Ok(
            read_index_documents(
                self._store,
                user_id,
                character_id=character_id,
                relationship_entity_id=relationship_entity_id,
            )
        )


def _memory_service(
    *,
    store: FilesystemMemoryStore | None = None,
    agent_profile_service: FilesystemAgentProfileService | None = None,
    character_id: str,
) -> FilesystemMemoryService:
    resolved_store = store or FilesystemMemoryStore(default_memory_root())
    return FilesystemMemoryService(
        index_query=_FilesystemProjectionQuery(resolved_store),
        agent_profile_service=agent_profile_service,
        character_id=character_id,
    )


def test_filesystem_agent_profile_service_loads_localized_bundle() -> None:
    """The bundled agent profile should load from localized front matter."""
    service = FilesystemAgentProfileService(
        store=FilesystemMemoryStore(Path("memory")),
        character_id="shirasagi-reina",
    )

    bundle = service.load_agent_profile_bundle()

    assert bundle.relationship_entity_id == "relationship:shirasagi-reina"
    assert bundle.relationship_entity_label == "白鷺レイナとの関係"
    assert bundle.relationship_entity_type == "relationship"
    assert bundle.relationship_tag == "agent-growth"
    assert bundle.relationship_defaults.stage == 0


@pytest.mark.anyio
async def test_filesystem_memory_service_build_context_returns_manifest_pack(
    tmp_path: Path,
) -> None:
    """The adapter should return the app-level memory DTO."""
    copy_agent_profile_bundle(tmp_path / "memory")
    character_id = _character_id()
    agent_profile_service = FilesystemAgentProfileService(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=character_id,
    )
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        agent_profile_service=agent_profile_service,
        character_id=character_id,
    )
    result = await service.build_context("u1")

    assert not is_err(result)
    pack = result.value
    assert isinstance(pack, MemoryContextPack)
    assert pack.user_id == "u1"
    assert pack.profile is not None
    assert pack.profile.user_id == "ai"
    assert pack.profile.display_name is None
    assert pack.timelines == []
    assert pack.entities == []
    assert pack.manifest_items
    assert "Memory manifest:" in (pack.assembled_context or "")
    assert any(item.memory_id == "agent_profile:soul" for item in pack.manifest_items)

    profile_dir = tmp_path / "memory" / "profiles" / "agent" / character_id
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
            preferences=["quiet places"],
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
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )

    result = await service.build_context("u1")

    assert not is_err(result)
    assert result.value.profile is not None
    assert result.value.profile.display_name == "ユーザーA"
    assert result.value.entities[0].label == "机"
    assert any(
        item.memory_id == "entity:ENT-001" for item in result.value.manifest_items
    )
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
async def test_filesystem_memory_service_reads_entity_by_memory_id(
    tmp_path: Path,
) -> None:
    """Detailed memory reads should keep properties and missing attributes."""
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )
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

    result = await service.read_memory("entity:project-x", "u1")

    assert not is_err(result)
    assert result.value.source.id == "project-x"
    assert result.value.memory_id == "entity:project-x"
    assert "language: Python" in result.value.rendered_text
    assert "ports: ai_service, memory_service" in result.value.rendered_text
    assert "missing_attributes: repository" in result.value.rendered_text


@pytest.mark.anyio
async def test_filesystem_memory_service_filters_non_selected_relationship_entity(
    tmp_path: Path,
) -> None:
    """Only the selected relationship entity should appear in memory context."""

    character_id = _character_id()
    copy_agent_profile_bundle(tmp_path / "memory")
    write_service = FilesystemMemoryWriteService(tmp_path / "memory")
    write_service.write_entity(
        MemoryEntity(
            id=f"relationship:{character_id}",
            user_id="u1",
            label="Selected relationship",
            entity_type="relationship",
            status="active",
            confidence=1.0,
        )
    )
    write_service.write_entity(
        MemoryEntity(
            id="relationship:someone-else",
            user_id="u1",
            label="Other relationship",
            entity_type="relationship",
            status="active",
            confidence=1.0,
        )
    )
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        agent_profile_service=FilesystemAgentProfileService(
            store=FilesystemMemoryStore(tmp_path / "memory"),
            character_id=character_id,
        ),
        character_id=character_id,
    )

    result = await service.build_context("u1")

    assert not is_err(result)
    manifest_ids = {item.memory_id for item in result.value.manifest_items}
    entity_labels = [entity.label for entity in result.value.entities]
    assert "entity:relationship:someone-else" not in manifest_ids
    assert entity_labels == ["Selected relationship"]


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
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )

    result = await service.build_context("u1")

    assert not is_err(result)
    assert len(result.value.timelines) == 1
    assert result.value.timelines[0].content == "remember this"
    timeline_manifest = [
        item for item in result.value.manifest_items if item.memory_type == "timeline"
    ]
    assert timeline_manifest
    assert timeline_manifest[0].memory_id.startswith("timeline:202")
    assert timeline_manifest[0].when is not None
    assert timeline_manifest[0].title == "remember this"
    assert timeline_manifest[0].summary == "remember this"
    assert f"{timeline_manifest[0].memory_id} | when={timeline_manifest[0].when}" in (
        result.value.assembled_context or ""
    )

    files = sorted((tmp_path / "memory" / "timeline" / "u1" / "raw").rglob("*.md"))
    assert len(files) == 1
    timeline_text = files[0].read_text(encoding="utf-8")
    assert timeline_text.startswith("---\n")
    assert "schema_version: 1" in timeline_text
    assert "memory_type: timeline" in timeline_text
    assert "timeline_type: raw" in timeline_text
    assert "memory_id: timeline:" in timeline_text
    assert "manifest_title: remember this" in timeline_text
    assert "manifest_summary: remember this" in timeline_text


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
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )
    malformed_file = (
        tmp_path / "memory" / "timeline" / "u1" / "raw" / "2026" / "05" / "bad.md"
    )
    malformed_file.parent.mkdir(parents=True, exist_ok=True)
    malformed_file.write_text("not front matter\n", encoding="utf-8")

    result = await service.build_context("u1")

    assert is_err(result)
    assert "missing YAML front matter" in str(result.error)


@pytest.mark.anyio
async def test_filesystem_memory_service_rejects_path_scope_mismatch(
    tmp_path: Path,
) -> None:
    """A file under one user scope must not claim another front matter user_id."""
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )
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

    result = await service.build_context("u1")

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
    service = _memory_service(character_id=_character_id())
    result = await service.build_context("u1")

    assert not is_err(result)
    assert (
        preferred_root / "profiles" / "agent" / _character_id() / "SOUL.md"
    ).exists()
    assert (
        preferred_root / "profiles" / "agent" / _character_id() / "AGENTS.md"
    ).exists()
    agents_text = (
        preferred_root / "profiles" / "agent" / _character_id() / "AGENTS.md"
    ).read_text(encoding="utf-8")
    assert "## Communication Style" in agents_text
    assert "## Known Constraints" in agents_text
    assert "Do not mention that you are an AI" in agents_text
    assert "Treat conversation like hosting a guest" in agents_text
    assert "Relational habits" in agents_text
    assert "at most one easy-to-answer question" in agents_text


@pytest.mark.anyio
async def test_filesystem_memory_service_accepts_projection_query(
    tmp_path: Path,
) -> None:
    """The service should resolve documents through its projection query."""
    copy_agent_profile_bundle(tmp_path / "memory")
    agent_profile_service = FilesystemAgentProfileService(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        character_id=_character_id(),
    )
    service = _memory_service(
        store=FilesystemMemoryStore(tmp_path / "memory"),
        agent_profile_service=agent_profile_service,
        character_id=_character_id(),
    )

    result = await service.build_context("u1")

    assert not is_err(result)
    assert result.value.profile is not None
