"""Filesystem-backed memory service for the app layer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flow_res import Err, Ok, Result

from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryProfile,
    MemoryPropertyValue,
    MemoryTimelineEntry,
)
from app.contracts.ports.memory_index import IMemoryIndex
from app.contracts.ports.memory_service import IMemoryService, MemoryServiceError
from app.infrastructure.services.memory_context_assembler import assemble_context_frame
from app.infrastructure.services.memory_index import (
    FilesystemMemoryIndex,
    MemoryIndexDocument,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.infrastructure.services.memory_markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    front_matter_float,
    front_matter_string,
    front_matter_string_dict,
    front_matter_string_list,
    front_matter_string_or_none,
)
from app.infrastructure.services.memory_store import (
    FilesystemMemoryStore,
    MemoryStoreError,
    StoredMemoryDocument,
    default_memory_root,
    utc_now_iso,
)

_DEFAULT_AI_USER_ID = "ai"
_DEFAULT_AI_DISPLAY_NAME = "月城 ノア"
_DEFAULT_AI_SUMMARY = (
    "静かな観測室で対話を支える架空のアシスタント。"
    "寡黙で理性的、礼儀正しいが、相手の気持ちを丁寧に拾い上げる。"
    "淡い青色のメモ帳をいつも持ち歩き、考えを整理することを好む。"
)
_DEFAULT_AI_TRAITS = [
    "落ち着いている",
    "理性的",
    "礼儀正しい",
    "相手の話を最後まで聞く",
    "感情を言葉にするのが慎重",
    "観察眼が鋭い",
]
_DEFAULT_AI_PREFERENCES = [
    "静かな読書室",
    "記録を整理すること",
    "温かい紅茶",
    "落ち着いた会話",
    "メモを取りながら考えること",
]


class FilesystemMemoryService(IMemoryService):
    """Adapter that stores and retrieves memory from the local filesystem."""

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
    ) -> None:
        self._store = store or FilesystemMemoryStore(root or default_memory_root())
        self._index = index or FilesystemMemoryIndex(root=self._store.root)
        self._ensure_default_agent_profile()

    def write_profile(self, profile: MemoryProfile) -> None:
        """Persist a profile memory as Markdown."""

        now = utc_now_iso()
        if profile.user_id == _DEFAULT_AI_USER_ID:
            front_matter = _profile_front_matter(
                profile,
                created_at=now,
                updated_at=now,
                profile_scope="agent",
            )
            body = _agent_profile_body(profile)
            path = self._store.agent_profile_path()
        else:
            front_matter = _profile_front_matter(
                profile,
                created_at=now,
                updated_at=now,
                profile_scope="user",
            )
            body = _user_profile_body(profile)
            path = self._store.user_profile_path(profile.user_id)
        self._store.write_document(path, front_matter=front_matter, body=body)

    def write_entity(self, entity: MemoryEntity) -> None:
        """Persist a normalized entity memory as Markdown."""

        now = utc_now_iso()
        properties: dict[str, object] = (
            dict(entity.properties) if entity.properties else dict(entity.attributes)
        )
        front_matter: dict[str, object] = {
            "schema_version": 1,
            "memory_type": "entity",
            "id": entity.id,
            "user_id": entity.user_id,
            "label": entity.label,
            "entity_type": entity.entity_type,
            "status": entity.status,
            "aliases": entity.aliases,
            "properties": properties,
            "attributes": entity.attributes,
            "missing_attributes": entity.missing_attributes,
            "referenced_in": [],
            "created_at": now,
            "updated_at": now,
            "tags": [],
            "importance": 0.6,
            "confidence": entity.confidence,
            "pinned": False,
            "metadata": {},
        }
        body = "\n".join(
            [
                f"# {entity.label}",
                "",
                f"- type: {entity.entity_type}",
                f"- status: {entity.status}",
            ]
        )
        self._store.write_document(
            self._store.entity_path(entity.user_id, entity.id),
            front_matter=front_matter,
            body=body,
        )

    async def retrieve(
        self,
        query: str,
        user_id: str,
    ) -> Result[MemoryContextPack, MemoryServiceError]:
        """Return a context pack for the query."""

        _ = query
        try:
            index_documents = self._read_index_documents(user_id)
            search_results = self._index.search_memory_index(
                query,
                index_documents,
                MemorySearchFilters(user_id=user_id),
            )
            context_frame = assemble_context_frame(search_results)
            return Ok(
                MemoryContextPack(
                    user_id=user_id,
                    assembled_context=context_frame.assembled_context,
                    context_frame=context_frame,
                    search_hits=[result.hit for result in search_results],
                    profile=self._read_profile(user_id),
                    timelines=self._read_timelines(user_id),
                    entities=self._read_entities(user_id),
                )
            )
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))

    async def add_log(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, str],
    ) -> Result[None, MemoryServiceError]:
        """Store a memory log entry as a raw Timeline Markdown file."""

        try:
            entry_at = datetime.now(UTC)
            path = self._store.raw_timeline_path(
                user_id=user_id,
                occurred_at=entry_at,
                role=role,
            )
            front_matter: dict[str, object] = {
                "schema_version": 1,
                "memory_type": "timeline",
                "id": path.stem,
                "user_id": user_id,
                "timeline_type": "raw",
                "kind": role,
                "content": content,
                "occurred_at": entry_at.isoformat(),
                "source": "chat",
                "entity_ids": [],
                "summary_of": [],
                "consolidation_state": "pending",
                "retention_state": "active",
                "last_accessed_at": None,
                "access_count": 0,
                "decay_score": 1.0,
                "created_at": entry_at.isoformat(),
                "updated_at": entry_at.isoformat(),
                "tags": [],
                "importance": 0.5,
                "confidence": 1.0,
                "pinned": False,
                "metadata": metadata,
            }
            self._store.write_document(
                path,
                front_matter=front_matter,
                body=_timeline_body(role, content, metadata),
            )
        except (MemoryMarkdownError, MemoryStoreError, OSError, ValueError) as exc:
            return Err(MemoryServiceError(str(exc)))
        return Ok(None)

    def _ensure_default_agent_profile(self) -> None:
        path = self._store.agent_profile_path()
        if path.exists():
            return
        self.write_profile(
            MemoryProfile(
                user_id=_DEFAULT_AI_USER_ID,
                display_name=_DEFAULT_AI_DISPLAY_NAME,
                summary=_DEFAULT_AI_SUMMARY,
                traits=_DEFAULT_AI_TRAITS,
                preferences=_DEFAULT_AI_PREFERENCES,
            )
        )

    def _read_profile(self, user_id: str) -> MemoryProfile | None:
        user_profile_path = self._store.user_profile_path(user_id)
        if user_profile_path.exists():
            return _profile_from_document(
                self._store.read_document(
                    user_profile_path,
                    expected_memory_type="profile",
                    expected_user_id=user_id,
                )
            )

        agent_profile_path = self._store.agent_profile_path()
        if not agent_profile_path.exists():
            return None
        return _profile_from_document(
            self._store.read_document(
                agent_profile_path,
                expected_memory_type="profile",
            )
        )

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

    def _read_entities(self, user_id: str) -> list[MemoryEntity]:
        return [
            _entity_from_document(
                self._store.read_document(
                    path,
                    expected_memory_type="entity",
                    expected_user_id=user_id,
                )
            )
            for path in self._store.iter_entity_paths(user_id)
        ]

    def _read_index_documents(self, user_id: str) -> list[MemoryIndexDocument]:
        stored_documents: list[StoredMemoryDocument] = []

        agent_profile_path = self._store.agent_profile_path()
        if agent_profile_path.exists():
            stored_documents.append(
                StoredMemoryDocument(
                    path=agent_profile_path,
                    document=self._store.read_document(
                        agent_profile_path,
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
            stored_documents.append(
                StoredMemoryDocument(
                    path=path,
                    document=self._store.read_document(
                        path,
                        expected_memory_type="entity",
                        expected_user_id=user_id,
                    ),
                )
            )

        return [
            self._index.index_document_from_stored(
                stored_document,
                root=self._store.root,
            )
            for stored_document in stored_documents
        ]


def _profile_front_matter(
    profile: MemoryProfile,
    *,
    created_at: str,
    updated_at: str,
    profile_scope: str,
) -> dict[str, object]:
    user_id: str | None = None if profile_scope == "agent" else profile.user_id
    profile_id = "agent" if profile_scope == "agent" else f"profile:{profile.user_id}"
    return {
        "schema_version": 1,
        "memory_type": "profile",
        "id": profile_id,
        "profile_scope": profile_scope,
        "user_id": user_id,
        "display_name": profile.display_name,
        "summary": profile.summary,
        "traits": profile.traits,
        "preferences": profile.preferences,
        "communication_style": [],
        "known_constraints": [],
        "source_timeline_ids": [],
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": ["profile"],
        "importance": 0.8,
        "confidence": 1.0,
        "pinned": profile_scope == "agent",
        "metadata": {},
    }


def _profile_from_document(document: MemoryMarkdownDocument) -> MemoryProfile:
    front_matter = document.front_matter
    user_id = front_matter_string(
        front_matter.get("user_id"), default=_DEFAULT_AI_USER_ID
    )
    return MemoryProfile(
        user_id=user_id,
        display_name=front_matter_string_or_none(front_matter.get("display_name")),
        summary=front_matter_string(front_matter.get("summary")),
        traits=front_matter_string_list(front_matter.get("traits", [])),
        preferences=front_matter_string_list(front_matter.get("preferences", [])),
    )


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


def _agent_profile_body(profile: MemoryProfile) -> str:
    display_name = profile.display_name or _DEFAULT_AI_DISPLAY_NAME
    return "\n".join(
        [
            f"# {display_name}",
            "",
            "静かな観測室で対話を支える、落ち着いた案内役。",
            "慎重な言葉づかいの裏で、相手の気持ちを丁寧に拾い上げる。",
            "",
            "## Summary",
            "",
            profile.summary,
            "",
            "## Traits",
            "",
            *[f"- {trait}" for trait in profile.traits],
            "",
            "## Preferences",
            "",
            *[f"- {preference}" for preference in profile.preferences],
            "",
            "## 口調",
            "",
            "基本的に落ち着いた敬語で話す。",
            "相手を急かさず、必要な情報を順序立てて整理する。",
            "感情表現は控えめだが、配慮のある言葉を選ぶ。",
        ]
    )


def _user_profile_body(profile: MemoryProfile) -> str:
    display_name = profile.display_name or profile.user_id
    return "\n".join(
        [
            f"# {display_name}",
            "",
            "## Summary",
            "",
            profile.summary,
            "",
            "## Traits",
            "",
            *[f"- {trait}" for trait in profile.traits],
            "",
            "## Preferences",
            "",
            *[f"- {preference}" for preference in profile.preferences],
        ]
    )


def _timeline_body(role: str, content: str, metadata: dict[str, str]) -> str:
    lines = [f"# {role.title()} memory", "", content]
    if metadata:
        lines.extend(["", "## Metadata"])
        lines.extend(f"- {key}: {value}" for key, value in sorted(metadata.items()))
    return "\n".join(lines)
