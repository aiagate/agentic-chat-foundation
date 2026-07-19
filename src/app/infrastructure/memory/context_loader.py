"""Helpers for loading filesystem-backed memory documents."""

from __future__ import annotations

from pathlib import Path

from app.contracts.messages.memory_context import (
    MemoryEntity,
    MemoryProfile,
    MemoryPropertyValue,
    MemoryTimelineEntry,
)
from app.contracts.messages.memory_index import MemoryIndexDocument
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    front_matter_float,
    front_matter_string,
    front_matter_string_dict,
    front_matter_string_list,
    front_matter_string_or_none,
)
from app.infrastructure.memory.store import FilesystemMemoryStore, StoredMemoryDocument


def read_index_documents(
    store: FilesystemMemoryStore,
    user_id: str,
) -> list[MemoryIndexDocument]:
    """Load the searchable documents needed for memory manifest and detail reads."""

    stored_documents: list[StoredMemoryDocument] = []
    stored_documents.extend(_user_profile_documents(store, user_id=user_id))
    stored_documents.extend(_timeline_documents(store, user_id=user_id))
    stored_documents.extend(
        _entity_documents(
            store,
            user_id=user_id,
        )
    )
    return [
        index_document_from_stored(stored_document, root=store.root)
        for stored_document in stored_documents
    ]


def profile_from_document(document: MemoryMarkdownDocument) -> MemoryProfile:
    """Convert a memory profile document into the app DTO."""

    front_matter = document.front_matter
    user_id = front_matter_string(front_matter.get("user_id"), default="ai")
    return MemoryProfile(
        user_id=user_id,
        display_name=front_matter_string_or_none(front_matter.get("display_name")),
        summary=front_matter_string(front_matter.get("summary")),
        traits=front_matter_string_list(front_matter.get("traits", [])),
        preferences=front_matter_string_list(front_matter.get("preferences", [])),
    )


def timeline_from_document(document: MemoryMarkdownDocument) -> MemoryTimelineEntry:
    """Convert a timeline document into the app DTO."""

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


def entity_from_document(document: MemoryMarkdownDocument) -> MemoryEntity:
    """Convert an entity document into the app DTO."""

    front_matter = document.front_matter
    raw_properties = front_matter.get("properties", {})
    return MemoryEntity(
        id=front_matter_string(front_matter["id"]),
        user_id=front_matter_string(front_matter["user_id"]),
        label=front_matter_string(front_matter["label"]),
        entity_type=front_matter_string(front_matter["entity_type"]),
        status=front_matter_string(front_matter.get("status", "active")),
        aliases=front_matter_string_list(front_matter.get("aliases", [])),
        properties=front_matter_property_dict(raw_properties),
        missing_attributes=front_matter_string_list(
            front_matter.get("missing_attributes", [])
        ),
        confidence=front_matter_float(front_matter.get("confidence"), default=1.0),
    )


def front_matter_property_dict(value: object) -> dict[str, MemoryPropertyValue]:
    """Normalize stored property values into the app contract shape."""

    if not isinstance(value, dict):
        return {}
    return {str(key): front_matter_property_value(item) for key, item in value.items()}


def front_matter_property_value(value: object) -> MemoryPropertyValue:
    """Normalize one stored property value into the app contract shape."""

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


def index_document_from_stored(
    stored: StoredMemoryDocument,
    *,
    root: Path,
) -> MemoryIndexDocument:
    """Build a searchable memory document with a stable relative reference."""

    return MemoryIndexDocument(
        path=stored.path,
        reference=relative_reference(stored.path, root),
        document=stored.document,
    )


def relative_reference(path: Path, root: Path) -> str:
    """Return a path relative to the memory root when possible."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _user_profile_documents(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
) -> list[StoredMemoryDocument]:
    user_profile_path = store.user_profile_path(user_id)
    if not user_profile_path.exists():
        return []
    return [
        StoredMemoryDocument(
            path=user_profile_path,
            document=store.read_document(
                user_profile_path,
                expected_memory_type="profile",
                expected_user_id=user_id,
            ),
        )
    ]


def _timeline_documents(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
) -> list[StoredMemoryDocument]:
    return [
        StoredMemoryDocument(
            path=path,
            document=store.read_document(
                path,
                expected_memory_type="timeline",
                expected_user_id=user_id,
            ),
        )
        for path in store.iter_timeline_paths(user_id)
    ]


def _entity_documents(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
) -> list[StoredMemoryDocument]:
    documents: list[StoredMemoryDocument] = []
    for path in store.iter_entity_paths(user_id):
        document = store.read_document(
            path,
            expected_memory_type="entity",
            expected_user_id=user_id,
        )
        if document.front_matter.get("entity_type") == "relationship":
            continue
        documents.append(StoredMemoryDocument(path=path, document=document))
    return documents
