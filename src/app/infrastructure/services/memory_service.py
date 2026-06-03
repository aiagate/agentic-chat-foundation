"""Filesystem-backed memory service for the app layer."""

from __future__ import annotations

from pathlib import Path

from flow_res import Err, Ok, Result, is_err

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import (
    CharacterDefinition,
    selected_character_definition,
)
from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
    MemoryPropertyValue,
    MemoryTimelineEntry,
)
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.embedding_service import IEmbeddingService
from app.contracts.ports.memory_index import IMemoryIndex
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.infrastructure import database
from app.infrastructure.memory.context_assembler import assemble_context_frame
from app.infrastructure.memory.embedding import (
    embed_text_deterministically,
)
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    front_matter_float,
    front_matter_string,
    front_matter_string_dict,
    front_matter_string_list,
    front_matter_string_or_none,
)
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    MemoryStoreError,
    StoredMemoryDocument,
    default_memory_root,
)
from app.infrastructure.queries.memory_index_query_service import (
    FilesystemMemoryIndex,
)


class FilesystemMemoryService(IMemoryService):
    """Adapter that retrieves memory from the local filesystem."""

    def __init__(
        self,
        root: Path | None = None,
        store: FilesystemMemoryStore | None = None,
        index: IMemoryIndex[
            StoredMemoryDocument,
            MemoryIndexDocument,
            MemorySearchResult,
            MemorySearchFilters,
        ]
        | None = None,
        embedding_service: IEmbeddingService | None = None,
        agent_profile_service: IAgentProfileService | None = None,
        character: CharacterDefinition | None = None,
    ) -> None:
        self._store = store or FilesystemMemoryStore(root or default_memory_root())
        self._index = index or FilesystemMemoryIndex(root=self._store.root)
        self._embedding_service = embedding_service
        self._agent_profile_service = agent_profile_service
        self._character = character or selected_character_definition()

    async def retrieve(
        self,
        query: str,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a context pack for the query."""

        _ = query
        try:
            profile_bundle = self._load_agent_profile_bundle()
            relationship_entity_id = (
                profile_bundle.relationship_entity_id
                if profile_bundle is not None
                else self._character.relationship_entity_id
            )
            index_documents = self._read_index_documents(
                user_id,
                relationship_entity_id=relationship_entity_id,
            )
            query_embedding = await self._query_embedding(query)
            search_results = self._index.search_memory_index(
                query,
                index_documents,
                MemorySearchFilters(
                    user_id=user_id,
                    relationship_entity_id=relationship_entity_id,
                ),
                root=self._store.root,
                index_db_path=database.get_sqlite_database_path(),
                embedding_service=self._embedding_service,
                query_embedding=query_embedding,
            )
            context_frame = assemble_context_frame(search_results)
            return Ok(
                MemoryContextPack(
                    user_id=user_id,
                    assembled_context=context_frame.assembled_context,
                    context_frame=context_frame,
                    search_hits=[result.hit for result in search_results],
                    profile=(
                        profile_bundle.profile
                        if profile_bundle is not None
                        else self._read_profile(user_id)
                    ),
                    timelines=self._read_timelines(user_id),
                    entities=self._read_entities(
                        user_id,
                        relationship_entity_id=relationship_entity_id,
                    ),
                )
            )
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))

    async def _query_embedding(self, query: str) -> list[float]:
        if self._embedding_service is None:
            return embed_text_deterministically(query)
        result = await self._embedding_service.embed_texts([query])
        if is_err(result) or not result.value:
            return embed_text_deterministically(query)
        return result.value[0]

    def _read_profile(self, user_id: str) -> MemoryProfile | None:
        if self._agent_profile_service is not None:
            try:
                return self._agent_profile_service.load_agent_profile_bundle().profile
            except Exception:
                pass
        agent_profile = _read_agent_profile_bundle(
            self._store,
            character_id=self._character.character_id,
        )
        if agent_profile is not None:
            return agent_profile

        user_profile_path = self._store.user_profile_path(user_id)
        if user_profile_path.exists():
            return _profile_from_document(
                self._store.read_document(
                    user_profile_path,
                    expected_memory_type="profile",
                    expected_user_id=user_id,
                )
            )

        return None

    def _read_timelines(self, user_id: str) -> list[MemoryTimelineEntry]:
        return [
            _timeline_from_document(
                self._store.read_document(
                    path,
                    expected_memory_type="timeline",
                    expected_user_id=user_id,
                )
            )
            for path in self._store.iter_timeline_paths(user_id)
        ]

    def _read_entities(
        self,
        user_id: str,
        *,
        relationship_entity_id: str,
    ) -> list[MemoryEntity]:
        return self._read_entities_for_relationship(
            user_id,
            relationship_entity_id=relationship_entity_id,
        )

    def _read_entities_for_relationship(
        self,
        user_id: str,
        *,
        relationship_entity_id: str,
    ) -> list[MemoryEntity]:
        entities: list[MemoryEntity] = []
        for path in self._store.iter_entity_paths(user_id):
            document = self._store.read_document(
                path,
                expected_memory_type="entity",
                expected_user_id=user_id,
            )
            if not _entity_is_selected_relationship(
                document,
                relationship_entity_id=relationship_entity_id,
            ):
                continue
            entities.append(_entity_from_document(document))
        return entities

    def _read_index_documents(
        self,
        user_id: str,
        *,
        relationship_entity_id: str,
    ) -> list[MemoryIndexDocument]:
        stored_documents: list[StoredMemoryDocument] = []

        for path in _agent_profile_paths(
            self._store,
            character_id=self._character.character_id,
        ):
            if path.exists():
                stored_documents.append(
                    StoredMemoryDocument(
                        path=path,
                        document=self._store.read_document(
                            path,
                            expected_memory_type="profile",
                        ),
                    )
                )

        user_profile_path = self._store.user_profile_path(user_id)
        if user_profile_path.exists():
            stored_documents.append(
                StoredMemoryDocument(
                    path=user_profile_path,
                    document=self._store.read_document(
                        user_profile_path,
                        expected_memory_type="profile",
                        expected_user_id=user_id,
                    ),
                )
            )

        for path in self._store.iter_timeline_paths(user_id):
            stored_documents.append(
                StoredMemoryDocument(
                    path=path,
                    document=self._store.read_document(
                        path,
                        expected_memory_type="timeline",
                        expected_user_id=user_id,
                    ),
                )
            )

        for path in self._store.iter_entity_paths(user_id):
            document = self._store.read_document(
                path,
                expected_memory_type="entity",
                expected_user_id=user_id,
            )
            if not _entity_is_selected_relationship(
                document,
                relationship_entity_id=relationship_entity_id,
            ):
                stored_documents.append(
                    StoredMemoryDocument(path=path, document=document)
                )
                continue
            stored_documents.append(StoredMemoryDocument(path=path, document=document))

        return [
            self._index.index_document_from_stored(
                stored_document,
                root=self._store.root,
            )
            for stored_document in stored_documents
        ]

    def _load_agent_profile_bundle(self) -> AgentProfileBundle | None:
        if self._agent_profile_service is None:
            return None
        try:
            return self._agent_profile_service.load_agent_profile_bundle()
        except Exception:
            return None


def _profile_from_document(document: MemoryMarkdownDocument) -> MemoryProfile:
    front_matter = document.front_matter
    user_id = front_matter_string(front_matter.get("user_id"), default="ai")
    return MemoryProfile(
        user_id=user_id,
        display_name=front_matter_string_or_none(front_matter.get("display_name")),
        summary=front_matter_string(front_matter.get("summary")),
        traits=front_matter_string_list(front_matter.get("traits", [])),
        preferences=front_matter_string_list(front_matter.get("preferences", [])),
    )


def _read_agent_profile_bundle(
    store: FilesystemMemoryStore,
    *,
    character_id: str,
) -> MemoryProfile | None:
    agents_path = _resolved_agent_profile_part_path(store, "AGENTS", character_id)
    soul_path = _resolved_agent_profile_part_path(store, "SOUL", character_id)
    personal_path = _resolved_agent_profile_part_path(store, "PERSONAL", character_id)
    memory_path = _resolved_agent_profile_part_path(store, "MEMORY", character_id)
    if (
        agents_path is None
        and soul_path is None
        and personal_path is None
        and memory_path is None
    ):
        return None

    agents_document = (
        store.read_document(agents_path, expected_memory_type="profile")
        if agents_path is not None
        else None
    )
    soul_document = (
        store.read_document(soul_path, expected_memory_type="profile")
        if soul_path is not None
        else None
    )
    personal_document = (
        store.read_document(personal_path, expected_memory_type="profile")
        if personal_path is not None
        else None
    )
    memory_document = (
        store.read_document(memory_path, expected_memory_type="profile")
        if memory_path is not None
        else None
    )
    if (
        agents_document is None
        and soul_document is None
        and personal_document is None
        and memory_document is None
    ):
        return None

    agents_front_matter = (
        agents_document.front_matter if agents_document is not None else {}
    )
    soul_front_matter = soul_document.front_matter if soul_document else {}
    personal_front_matter = personal_document.front_matter if personal_document else {}
    soul_body = soul_document.body if soul_document is not None else ""
    personal_body = personal_document.body if personal_document is not None else ""
    memory_body = memory_document.body if memory_document is not None else ""
    return MemoryProfile(
        user_id=front_matter_string(agents_front_matter.get("user_id"), default="ai"),
        display_name=front_matter_string_or_none(
            agents_front_matter.get("display_name")
            or soul_front_matter.get("display_name")
            or personal_front_matter.get("display_name")
            or _body_h1_text(soul_body)
            or _body_h1_text(personal_body)
        ),
        summary=front_matter_string(
            soul_front_matter.get("summary")
            or _body_section_text(soul_body, "Summary")
            or _body_section_text(memory_body, "Stable notes"),
            default="",
        ),
        traits=front_matter_string_list(soul_front_matter.get("traits", []))
        or _body_section_list(soul_body, "Traits"),
        preferences=front_matter_string_list(
            personal_front_matter.get("preferences", [])
        )
        or _body_section_list(personal_body, "Preferences"),
    )


def _body_section_text(body: str, section_name: str) -> str:
    lines = _body_section_lines(body, section_name)
    return "\n".join(line.strip() for line in lines).strip()


def _body_section_list(body: str, section_name: str) -> list[str]:
    lines = _body_section_lines(body, section_name)
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
    return values


def _body_section_lines(body: str, section_name: str) -> list[str]:
    if not body:
        return []
    lines = body.splitlines()
    captured: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            active = stripped[3:].strip().lower() == section_name.lower()
            continue
        if active:
            captured.append(line)
    return captured


def _body_h1_text(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            value = stripped[2:].strip()
            if value:
                return value
    return None


def _agent_profile_paths(
    store: FilesystemMemoryStore,
    *,
    character_id: str,
) -> list[Path]:
    resolved_paths: list[Path] = []
    for part in ("AGENTS", "SOUL", "PERSONAL", "MEMORY"):
        path = _resolved_agent_profile_part_path(store, part, character_id)
        if path is not None and path.exists():
            resolved_paths.append(path)
    return resolved_paths


def _resolved_agent_profile_part_path(
    store: FilesystemMemoryStore,
    part: str,
    character_id: str,
) -> Path | None:
    namespaced_path = store.agent_profile_part_path(
        part,
        character_id=character_id,
    )
    if namespaced_path.exists():
        return namespaced_path

    legacy_path = _legacy_agent_profile_part_path(store.root, part)
    if legacy_path.exists():
        return legacy_path

    return None


def _legacy_agent_profile_part_path(root: Path, part: str) -> Path:
    normalized = part.upper()
    return root / "profiles" / "agent" / f"{normalized}.md"


def _timeline_from_document(
    document: MemoryMarkdownDocument,
) -> MemoryTimelineEntry:
    front_matter = document.front_matter
    return MemoryTimelineEntry(
        id=front_matter_string(front_matter["id"]),
        user_id=front_matter_string(front_matter["user_id"]),
        kind=front_matter_string(front_matter["kind"]),
        content=front_matter_string(front_matter["content"]),
        occurred_at=front_matter_string(front_matter["occurred_at"]),
        source=front_matter_string(front_matter["source"]),
        entity_ids=front_matter_string_list(front_matter.get("entity_ids", [])),
        metadata=front_matter_string_dict(front_matter.get("metadata", {})),
    )


def _entity_from_document(document: MemoryMarkdownDocument) -> MemoryEntity:
    front_matter = document.front_matter
    raw_properties = front_matter.get("properties", front_matter.get("attributes", {}))
    raw_attributes = front_matter.get("attributes", raw_properties)
    return MemoryEntity(
        id=front_matter_string(front_matter["id"]),
        user_id=front_matter_string(front_matter["user_id"]),
        label=front_matter_string(front_matter["label"]),
        entity_type=front_matter_string(front_matter["entity_type"]),
        status=front_matter_string(front_matter.get("status", "active")),
        aliases=front_matter_string_list(front_matter.get("aliases", [])),
        attributes=front_matter_string_dict(raw_attributes),
        properties=_front_matter_property_dict(raw_properties),
        missing_attributes=front_matter_string_list(
            front_matter.get("missing_attributes", [])
        ),
        confidence=front_matter_float(front_matter.get("confidence"), default=1.0),
    )


def _entity_is_selected_relationship(
    document: MemoryMarkdownDocument,
    *,
    relationship_entity_id: str,
) -> bool:
    front_matter = document.front_matter
    if front_matter.get("entity_type") != "relationship":
        return True
    if not relationship_entity_id:
        return True
    return front_matter_string(front_matter.get("id")) == relationship_entity_id


def _front_matter_property_dict(value: object) -> dict[str, MemoryPropertyValue]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _front_matter_property_value(item) for key, item in value.items()}


def _front_matter_property_value(value: object) -> MemoryPropertyValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        scalar_values: list[str | int | float | bool] = []
        for item in value:
            if isinstance(item, str | int | float | bool):
                scalar_values.append(item)
            else:
                scalar_values.append(front_matter_string(item))
        return scalar_values
    return front_matter_string(value)
