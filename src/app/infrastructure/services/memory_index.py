"""Persistent memory index with deterministic fallback search."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import unquote

from flow_res import Err, Ok, Result

from app.contracts.messages.memory_context import (
    MemorySearchHit,
    MemorySource,
    MemoryType,
)
from app.contracts.ports.memory_index import IMemoryIndex, MemoryIndexError
from app.infrastructure.services.memory_embedding import (
    embed_text_deterministically,
)
from app.infrastructure.services.memory_markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
    render_memory_markdown,
)
from app.infrastructure.services.memory_store import (
    FilesystemMemoryStore,
    StoredMemoryDocument,
    default_memory_root,
)

_TERM_PATTERN = re.compile(r"[\w一-龯ぁ-んァ-ヶー]+", re.UNICODE)
_INDEX_DB_NAME = "memory_index.sqlite3"
_INDEX_TABLE_NAME = "memory_index_documents"
_INDEX_AGENT_REFERENCE = "profiles/agent.md"


@dataclass(frozen=True, slots=True)
class MemorySearchFilters:
    """Filters supported by the local memory keyword index."""

    user_id: str
    memory_type: MemoryType | None = None
    tags: tuple[str, ...] = ()
    date_from: datetime | str | None = None
    date_to: datetime | str | None = None
    status: str | None = None
    unresolved: bool | None = None
    timeline_type: str | None = None
    retention_state: str | None = None
    entity_type: str | None = None
    consolidation_state: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryIndexDocument:
    """Searchable view of a parsed memory document."""

    path: Path
    reference: str
    document: MemoryMarkdownDocument


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """Search hit paired with the document used for assembly."""

    hit: MemorySearchHit
    document: MemoryIndexDocument
    rank_score: float = field(compare=True)


@dataclass(frozen=True, slots=True)
class MemoryIndexRow:
    """Persisted metadata projection for a memory document."""

    row_id: str
    user_id: str | None
    memory_type: str
    source_path: str
    source_id: str
    title: str | None
    content_hash: str
    indexed_text: str
    tags_json: str
    status: str | None
    timeline_type: str | None
    occurred_at: str | None
    updated_at: str
    importance: float
    confidence: float
    decay_score: float

    def as_tuple(self) -> tuple[object, ...]:
        """Return a parameter tuple for SQLite upsert statements."""

        return (
            self.row_id,
            self.user_id,
            self.memory_type,
            self.source_path,
            self.source_id,
            self.title,
            self.content_hash,
            self.indexed_text,
            self.tags_json,
            self.status,
            self.timeline_type,
            self.occurred_at,
            self.updated_at,
            self.importance,
            self.confidence,
            self.decay_score,
        )


@dataclass(frozen=True, slots=True)
class FilesystemMemoryIndex(
    IMemoryIndex[
        StoredMemoryDocument,
        MemoryIndexDocument,
        MemorySearchResult,
        MemorySearchFilters,
    ]
):
    """Deterministic memory index backed by SQLite metadata rows."""

    root: Path | None = None

    def index_document_from_stored(
        self,
        stored: StoredMemoryDocument,
        *,
        root: Path,
    ) -> MemoryIndexDocument:
        """Build an index document with a stable relative memory reference."""

        return index_document_from_stored(stored, root=root)

    def search_memory_index(
        self,
        query: str,
        documents: Sequence[MemoryIndexDocument],
        filters: MemorySearchFilters,
        *,
        limit: int = 20,
    ) -> list[MemorySearchResult]:
        """Search memory documents using deterministic keyword scoring."""

        if not documents:
            documents = self._load_index_documents(filters.user_id)
        return search_memory_index(query, documents, filters, limit=limit)

    def rebuild_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Rebuild the persistent index snapshot from Markdown documents."""

        try:
            return _rebuild_or_repair_index(
                self._store(),
                self._index_db_path(),
                user_id=user_id,
                repair=False,
            )
        except (MemoryMarkdownError, OSError, sqlite3.Error, ValueError) as exc:
            return Err(MemoryIndexError(str(exc)))

    def repair_memory_index(
        self,
        *,
        user_id: str | None = None,
    ) -> Result[int, MemoryIndexError]:
        """Repair stale rows in the persistent index snapshot."""

        try:
            return _rebuild_or_repair_index(
                self._store(),
                self._index_db_path(),
                user_id=user_id,
                repair=True,
            )
        except (MemoryMarkdownError, OSError, sqlite3.Error, ValueError) as exc:
            return Err(MemoryIndexError(str(exc)))

    def _store(self) -> FilesystemMemoryStore:
        root = self.root or default_memory_root()
        return FilesystemMemoryStore(root)

    def _index_db_path(self) -> Path:
        return (self.root or default_memory_root()) / "index" / _INDEX_DB_NAME

    def _load_index_documents(self, user_id: str) -> list[MemoryIndexDocument]:
        try:
            with sqlite3.connect(self._index_db_path()) as connection:
                _ensure_index_schema(connection)
                rows = connection.execute(
                    f"""
                    select source_path, memory_type, user_id
                    from {_INDEX_TABLE_NAME}
                    where user_id = ?
                       or (user_id is null and source_path = ?)
                    order by source_path
                    """,
                    (user_id, _INDEX_AGENT_REFERENCE),
                ).fetchall()
        except sqlite3.Error:
            return []

        documents: list[MemoryIndexDocument] = []
        store = self._store()
        for source_path, memory_type, row_user_id in rows:
            path = self._resolve_index_path(source_path)
            if not path.exists():
                continue
            try:
                document = store.read_document(
                    path,
                    expected_memory_type=cast(str, memory_type),
                    expected_user_id=cast(str | None, row_user_id),
                )
            except MemoryMarkdownError:
                raise
            documents.append(
                MemoryIndexDocument(
                    path=path,
                    reference=source_path,
                    document=document,
                )
            )
        return documents

    def _resolve_index_path(self, source_path: str) -> Path:
        path = Path(source_path)
        if path.is_absolute():
            return path
        return (self.root or default_memory_root()) / path


def index_document_from_stored(
    stored: StoredMemoryDocument,
    *,
    root: Path,
) -> MemoryIndexDocument:
    """Build an index document with a stable relative memory reference."""

    try:
        reference = stored.path.relative_to(root).as_posix()
    except ValueError:
        reference = stored.path.as_posix()
    return MemoryIndexDocument(
        path=stored.path,
        reference=reference,
        document=stored.document,
    )


def search_memory_index(
    query: str,
    documents: Sequence[MemoryIndexDocument],
    filters: MemorySearchFilters,
    *,
    limit: int = 20,
) -> list[MemorySearchResult]:
    """Search memory documents using deterministic keyword scoring."""

    terms = _query_terms(query)
    query_embedding = embed_text_deterministically(" ".join(terms)) if terms else []
    results: list[MemorySearchResult] = []

    for index_document in documents:
        front_matter = index_document.document.front_matter
        if not _passes_filters(front_matter, filters):
            continue

        indexed_text = _indexed_text(front_matter, index_document.document.body)
        tags_text = " ".join(front_matter_string_list(front_matter.get("tags")))
        matched_terms = _matched_terms(terms, [indexed_text, tags_text])
        if terms and not matched_terms and not _always_include(front_matter):
            continue

        score = _score_document(
            front_matter,
            terms=terms,
            matched_terms=matched_terms,
            indexed_text=indexed_text,
            query_embedding=query_embedding,
        )
        if score <= 0.0:
            continue

        source = _source_from_document(index_document)
        results.append(
            MemorySearchResult(
                hit=MemorySearchHit(
                    source=source,
                    score=round(score, 6),
                    matched_terms=matched_terms,
                    excerpt=_excerpt(front_matter, index_document.document.body),
                ),
                document=index_document,
                rank_score=score,
            )
        )

    return sorted(
        results,
        key=lambda result: (
            result.rank_score,
            _memory_type_priority(result.document.document.front_matter),
            result.hit.source.reference or "",
        ),
        reverse=True,
    )[:limit]


def _rebuild_or_repair_index(
    store: FilesystemMemoryStore,
    index_db_path: Path,
    *,
    user_id: str | None,
    repair: bool,
) -> Result[int, MemoryIndexError]:
    index_db_path.parent.mkdir(parents=True, exist_ok=True)
    stored_documents = _stored_documents_for_index(store, user_id=user_id)
    index_documents = [
        index_document_from_stored(stored_document, root=store.root)
        for stored_document in stored_documents
    ]
    index_rows = {
        document.reference: _row_from_index_document(document)
        for document in index_documents
    }
    scope_user_ids = {user_id} if user_id is not None else None

    with sqlite3.connect(index_db_path) as connection:
        _ensure_index_schema(connection)
        if not repair:
            _clear_index_scope(connection, scope_user_ids)
        else:
            _remove_missing_rows(connection, index_rows, scope_user_ids)
        changed_count = _upsert_index_rows(connection, index_rows)
        connection.commit()
    return Ok(changed_count)


def _stored_documents_for_index(
    store: FilesystemMemoryStore,
    *,
    user_id: str | None,
) -> list[StoredMemoryDocument]:
    if user_id is None:
        return _all_stored_documents(store)
    return _stored_documents_for_user(store, user_id=user_id)


def _stored_documents_for_user(
    store: FilesystemMemoryStore,
    *,
    user_id: str,
) -> list[StoredMemoryDocument]:
    stored_documents: list[StoredMemoryDocument] = []

    agent_profile_path = store.agent_profile_path()
    if agent_profile_path.exists():
        stored_documents.append(
            StoredMemoryDocument(
                path=agent_profile_path,
                document=store.read_document(
                    agent_profile_path,
                    expected_memory_type="profile",
                ),
            )
        )

    user_profile_path = store.user_profile_path(user_id)
    if user_profile_path.exists():
        stored_documents.append(
            StoredMemoryDocument(
                path=user_profile_path,
                document=store.read_document(
                    user_profile_path,
                    expected_memory_type="profile",
                    expected_user_id=user_id,
                ),
            )
        )

    for path in store.iter_timeline_paths(user_id):
        stored_documents.append(
            StoredMemoryDocument(
                path=path,
                document=store.read_document(
                    path,
                    expected_memory_type="timeline",
                    expected_user_id=user_id,
                ),
            )
        )

    for path in store.iter_entity_paths(user_id):
        stored_documents.append(
            StoredMemoryDocument(
                path=path,
                document=store.read_document(
                    path,
                    expected_memory_type="entity",
                    expected_user_id=user_id,
                ),
            )
        )

    return stored_documents


def _all_stored_documents(store: FilesystemMemoryStore) -> list[StoredMemoryDocument]:
    stored_documents: list[StoredMemoryDocument] = []

    agent_profile_path = store.agent_profile_path()
    if agent_profile_path.exists():
        stored_documents.append(
            StoredMemoryDocument(
                path=agent_profile_path,
                document=store.read_document(
                    agent_profile_path,
                    expected_memory_type="profile",
                ),
            )
        )

    profiles_root = store.root / "profiles" / "users"
    if profiles_root.exists():
        for path in sorted(profiles_root.glob("*.md")):
            user_id = unquote(path.stem)
            stored_documents.append(
                StoredMemoryDocument(
                    path=path,
                    document=store.read_document(
                        path,
                        expected_memory_type="profile",
                        expected_user_id=user_id,
                    ),
                )
            )

    for timeline_path in sorted((store.root / "timeline").rglob("*.md")):
        user_id = _path_segment_after_root(store.root / "timeline", timeline_path)
        stored_documents.append(
            StoredMemoryDocument(
                path=timeline_path,
                document=store.read_document(
                    timeline_path,
                    expected_memory_type="timeline",
                    expected_user_id=user_id,
                ),
            )
        )

    for entity_path in sorted((store.root / "entities").rglob("*.md")):
        user_id = _path_segment_after_root(store.root / "entities", entity_path)
        stored_documents.append(
            StoredMemoryDocument(
                path=entity_path,
                document=store.read_document(
                    entity_path,
                    expected_memory_type="entity",
                    expected_user_id=user_id,
                ),
            )
        )

    return stored_documents


def _path_segment_after_root(root: Path, path: Path) -> str:
    return unquote(path.relative_to(root).parts[0])


def _ensure_index_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        create table if not exists {_INDEX_TABLE_NAME} (
            id text primary key,
            user_id text,
            memory_type text not null,
            source_path text not null,
            source_id text not null,
            title text,
            content_hash text not null,
            indexed_text text not null,
            tags_json text not null,
            status text,
            timeline_type text,
            occurred_at text,
            updated_at text not null,
            importance real not null,
            confidence real not null,
            decay_score real not null
        )
        """
    )
    connection.execute(
        f"""
        create index if not exists idx_{_INDEX_TABLE_NAME}_user_id
        on {_INDEX_TABLE_NAME}(user_id)
        """
    )
    connection.execute(
        f"""
        create index if not exists idx_{_INDEX_TABLE_NAME}_source_id
        on {_INDEX_TABLE_NAME}(source_id)
        """
    )
    connection.execute(
        f"""
        create index if not exists idx_{_INDEX_TABLE_NAME}_content_hash
        on {_INDEX_TABLE_NAME}(content_hash)
        """
    )


def _clear_index_scope(
    connection: sqlite3.Connection,
    user_ids: set[str] | None,
) -> None:
    if user_ids is None:
        connection.execute(f"delete from {_INDEX_TABLE_NAME}")
        return
    for user_id in user_ids:
        connection.execute(
            f"""
            delete from {_INDEX_TABLE_NAME}
            where user_id = ?
               or (user_id is null and source_path = ?)
            """,
            (user_id, _INDEX_AGENT_REFERENCE),
        )


def _remove_missing_rows(
    connection: sqlite3.Connection,
    index_rows: dict[str, MemoryIndexRow],
    user_ids: set[str] | None,
) -> None:
    cursor = connection.execute(
        f"select id, user_id, source_path from {_INDEX_TABLE_NAME}"
    )
    current_source_paths = {row.source_path for row in index_rows.values()}
    for row_id, row_user_id, source_path in cursor.fetchall():
        if (
            user_ids is not None
            and row_user_id not in user_ids
            and source_path != _INDEX_AGENT_REFERENCE
        ):
            continue
        if source_path not in current_source_paths:
            connection.execute(
                f"delete from {_INDEX_TABLE_NAME} where id = ?",
                (row_id,),
            )


def _upsert_index_rows(
    connection: sqlite3.Connection,
    index_rows: dict[str, MemoryIndexRow],
) -> int:
    changed_count = 0
    for row in index_rows.values():
        connection.execute(
            f"""
            insert into {_INDEX_TABLE_NAME} (
                id,
                user_id,
                memory_type,
                source_path,
                source_id,
                title,
                content_hash,
                indexed_text,
                tags_json,
                status,
                timeline_type,
                occurred_at,
                updated_at,
                importance,
                confidence,
                decay_score
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                user_id = excluded.user_id,
                memory_type = excluded.memory_type,
                source_path = excluded.source_path,
                source_id = excluded.source_id,
                title = excluded.title,
                content_hash = excluded.content_hash,
                indexed_text = excluded.indexed_text,
                tags_json = excluded.tags_json,
                status = excluded.status,
                timeline_type = excluded.timeline_type,
                occurred_at = excluded.occurred_at,
                updated_at = excluded.updated_at,
                importance = excluded.importance,
                confidence = excluded.confidence,
                decay_score = excluded.decay_score
            """,
            row.as_tuple(),
        )
        changed_count += 1
    return changed_count


def _row_from_index_document(
    index_document: MemoryIndexDocument,
) -> MemoryIndexRow:
    front_matter = index_document.document.front_matter
    source_path = index_document.reference
    body = index_document.document.body
    indexed_text = _indexed_text(front_matter, body)
    content_hash = hashlib.sha256(
        render_memory_markdown(
            front_matter,
            body,
            location=index_document.reference,
        ).encode("utf-8")
    ).hexdigest()
    user_id = front_matter.get("user_id")
    if not isinstance(user_id, str):
        user_id = None
    return MemoryIndexRow(
        row_id=source_path,
        user_id=user_id,
        memory_type=front_matter_string(front_matter.get("memory_type")),
        source_path=source_path,
        source_id=front_matter_string(front_matter.get("id")),
        title=_title(front_matter),
        content_hash=content_hash,
        indexed_text=indexed_text,
        tags_json=json.dumps(
            front_matter_string_list(front_matter.get("tags")),
            ensure_ascii=False,
            sort_keys=True,
        ),
        status=front_matter_string_or_none(front_matter.get("status")),
        timeline_type=front_matter_string_or_none(front_matter.get("timeline_type")),
        occurred_at=front_matter_string_or_none(front_matter.get("occurred_at")),
        updated_at=front_matter_string(front_matter.get("updated_at")),
        importance=_float_value(front_matter.get("importance"), default=0.5),
        confidence=_float_value(front_matter.get("confidence"), default=1.0),
        decay_score=_float_value(front_matter.get("decay_score"), default=1.0),
    )


def _passes_filters(
    front_matter: Mapping[str, object],
    filters: MemorySearchFilters,
) -> bool:
    memory_type = front_matter.get("memory_type")
    if memory_type not in {"profile", "timeline", "entity"}:
        return False
    if filters.memory_type is not None and memory_type != filters.memory_type:
        return False
    if not _passes_user_scope(front_matter, filters.user_id):
        return False
    if not _passes_tags(front_matter, filters.tags):
        return False
    if not _passes_date_range(front_matter, filters.date_from, filters.date_to):
        return False

    if memory_type == "entity":
        if filters.status is not None and front_matter.get("status") != filters.status:
            return False
        if (
            filters.entity_type is not None
            and front_matter.get("entity_type") != filters.entity_type
        ):
            return False
        if filters.unresolved is not None:
            unresolved = _is_unresolved(front_matter)
            if unresolved is not filters.unresolved:
                return False
    elif filters.status is not None or filters.entity_type is not None:
        return False

    if memory_type == "timeline":
        if (
            filters.timeline_type is not None
            and front_matter.get("timeline_type") != filters.timeline_type
        ):
            return False
        if (
            filters.consolidation_state is not None
            and front_matter.get("consolidation_state") != filters.consolidation_state
        ):
            return False
    elif filters.timeline_type is not None or filters.consolidation_state is not None:
        return False

    retention_state = str(front_matter.get("retention_state") or "active")
    if filters.retention_state is None:
        return retention_state != "archived" or front_matter.get("pinned") is True
    return retention_state == filters.retention_state


def _passes_user_scope(front_matter: Mapping[str, object], user_id: str) -> bool:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile" and front_matter.get("profile_scope") == "agent":
        return True
    return front_matter.get("user_id") == user_id


def _passes_tags(front_matter: Mapping[str, object], tags: tuple[str, ...]) -> bool:
    if not tags:
        return True
    document_tags = {
        tag.lower() for tag in front_matter_string_list(front_matter.get("tags"))
    }
    return all(tag.lower() in document_tags for tag in tags)


def _passes_date_range(
    front_matter: Mapping[str, object],
    date_from: datetime | str | None,
    date_to: datetime | str | None,
) -> bool:
    if date_from is None and date_to is None:
        return True
    value = _date_value(
        front_matter.get("occurred_at")
        or front_matter.get("created_at")
        or front_matter.get("updated_at")
    )
    if value is None:
        return False
    parsed_from = _date_value(date_from)
    parsed_to = _date_value(date_to)
    if parsed_from is not None and value < parsed_from:
        return False
    if parsed_to is not None and value > parsed_to:
        return False
    return True


def _indexed_text(
    front_matter: Mapping[str, object],
    body: str,
) -> str:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        fields = [
            "display_name",
            "summary",
            "traits",
            "preferences",
            "communication_style",
            "known_constraints",
            "tags",
        ]
    elif memory_type == "timeline":
        fields = ["content", "kind", "source", "entity_ids", "tags", "metadata"]
    else:
        fields = [
            "label",
            "entity_type",
            "status",
            "aliases",
            "properties",
            "attributes",
            "missing_attributes",
            "referenced_in",
            "tags",
        ]

    indexed = [_stringify(front_matter.get(field_name)) for field_name in fields]
    metadata = _stringify(front_matter.get("metadata"))
    if metadata:
        indexed.append(metadata)
    if body:
        indexed.append(body)
    return "\n".join(part for part in indexed if part).strip()


def _score_document(
    front_matter: Mapping[str, object],
    *,
    terms: list[str],
    matched_terms: list[str],
    indexed_text: str,
    query_embedding: list[float],
) -> float:
    memory_type = front_matter.get("memory_type")
    importance = _float_value(front_matter.get("importance"), default=0.5)
    confidence = _float_value(front_matter.get("confidence"), default=1.0)
    decay_score = _float_value(front_matter.get("decay_score"), default=1.0)
    score = (0.20 * importance) + (0.15 * confidence) + (0.10 * decay_score)

    if not terms:
        if _always_include(front_matter):
            return score
        return 0.0

    searchable_text = indexed_text.lower()
    for term in matched_terms:
        score += 1.0 + min(searchable_text.count(term), 3) * 0.15

    semantic_score = _semantic_score(query_embedding, indexed_text)
    score += semantic_score * 0.75

    if memory_type == "entity":
        score += _entity_match_boost(front_matter, terms)
        if _is_unresolved(front_matter) and _mentions_unknowns(terms):
            score += 0.45
        if front_matter.get("status") == "deprecated":
            score *= 0.70
        if front_matter.get("status") == "merged":
            score *= 0.60
    elif memory_type == "timeline":
        if front_matter.get("timeline_type") == "daily_summary":
            score += 0.25
        elif front_matter.get("timeline_type") == "raw":
            score *= 0.90
    elif memory_type == "profile":
        score *= 0.85

    return score


def _semantic_score(query_embedding: list[float], indexed_text: str) -> float:
    if not query_embedding:
        return 0.0
    document_embedding = embed_text_deterministically(indexed_text)
    return _cosine_similarity(query_embedding, document_embedding)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0.0:
        return 0.0
    numerator = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    return numerator / denominator


def _entity_match_boost(
    front_matter: Mapping[str, object],
    terms: Iterable[str],
) -> float:
    labels = [front_matter_string(front_matter.get("label"))]
    labels.extend(front_matter_string_list(front_matter.get("aliases")))
    normalized_labels = {label.lower() for label in labels if label}
    boost = 0.0
    for term in terms:
        if term in normalized_labels:
            boost += 1.5
        elif any(term in label for label in normalized_labels):
            boost += 0.6
    return boost


def _source_from_document(index_document: MemoryIndexDocument) -> MemorySource:
    front_matter = index_document.document.front_matter
    memory_type = cast(MemoryType, front_matter["memory_type"])
    return MemorySource(
        id=front_matter_string(front_matter["id"]),
        memory_type=memory_type,
        title=_title(front_matter),
        user_id=_source_user_id(front_matter),
        reference=index_document.reference,
    )


def _source_user_id(front_matter: Mapping[str, object]) -> str | None:
    if front_matter.get("profile_scope") == "agent":
        return None
    value = front_matter.get("user_id")
    if isinstance(value, str):
        return value
    return None


def _title(front_matter: Mapping[str, object]) -> str | None:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        return front_matter_string_or_none(front_matter.get("display_name"))
    if memory_type == "entity":
        return front_matter_string_or_none(front_matter.get("label"))
    if memory_type == "timeline":
        return front_matter_string_or_none(front_matter.get("kind"))
    return None


def _excerpt(front_matter: Mapping[str, object], body: str) -> str:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        text = front_matter_string(front_matter.get("summary")) or body
    elif memory_type == "timeline":
        text = front_matter_string(front_matter.get("content")) or body
    elif memory_type == "entity":
        text = body or front_matter_string(front_matter.get("label"))
    else:
        text = body
    normalized = " ".join(text.split())
    if len(normalized) <= 240:
        return normalized
    return f"{normalized[:237]}..."


def _matched_terms(terms: list[str], values: Iterable[str]) -> list[str]:
    haystack = "\n".join(values).lower()
    return [term for term in terms if term in haystack]


def _query_terms(query: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for match in _TERM_PATTERN.finditer(query.lower()):
        term = match.group(0)
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _always_include(front_matter: Mapping[str, object]) -> bool:
    return (
        front_matter.get("memory_type") == "profile"
        and front_matter.get("profile_scope") == "agent"
    )


def _is_unresolved(front_matter: Mapping[str, object]) -> bool:
    return front_matter.get("status") == "unresolved" or bool(
        front_matter_string_list(front_matter.get("missing_attributes"))
    )


def _mentions_unknowns(terms: Iterable[str]) -> bool:
    unknown_terms = {"unknown", "missing", "unresolved", "未解決", "不明", "不足"}
    return any(term in unknown_terms for term in terms)


def _memory_type_priority(front_matter: Mapping[str, object]) -> int:
    memory_type = front_matter.get("memory_type")
    if memory_type == "entity":
        return 3
    if memory_type == "profile":
        return 2
    if memory_type == "timeline":
        return 1
    return 0


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_stringify(item))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _float_value(value: object, *, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, str | int | float):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0.0), 1.0)


def _date_value(value: datetime | str | object | None) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
