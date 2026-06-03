"""Memory index search service."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

from flow_res import is_err

from app.contracts.messages.memory_context import MemorySearchHit, MemorySource
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemoryIndexRecord,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.contracts.ports.embedding_service import IEmbeddingService
from app.contracts.ports.memory_index import IMemoryIndex
from app.infrastructure.memory.decay import calculate_decay_score
from app.infrastructure.memory.embedding import (
    embed_text_deterministically,
)
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
    render_memory_markdown,
)
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    StoredMemoryDocument,
    default_memory_root,
)

_TERM_PATTERN = re.compile(r"[\w一-龯ぁ-んァ-ヶー]+", re.UNICODE)
_SEMANTIC_FALLBACK_THRESHOLD = 0.55
_AGENT_PROFILE_PATH = "profiles/agent/SOUL.md"


class FilesystemMemoryIndex(
    IMemoryIndex[
        StoredMemoryDocument,
        MemoryIndexDocument,
        MemorySearchResult,
        MemorySearchFilters,
    ]
):
    """Search memory index documents."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        embedding_service: IEmbeddingService | None = None,
    ) -> None:
        self._root = root or default_memory_root()
        self._store = FilesystemMemoryStore(self._root)
        self._embedding_service = embedding_service

    def index_document_from_stored(
        self,
        stored: StoredMemoryDocument,
        *,
        root: Path,
    ) -> MemoryIndexDocument:
        """Build a searchable document with a stable reference."""

        return MemoryIndexDocument(
            path=stored.path,
            reference=_relative_reference(stored.path, root),
            document=stored.document,
        )

    def search_memory_index(
        self,
        query: str,
        documents: Sequence[MemoryIndexDocument],
        filters: MemorySearchFilters,
        *,
        root: Path | None = None,
        index_db_path: Path | None = None,
        embedding_service: object | None = None,
        query_embedding: list[float] | None = None,
        limit: int = 20,
    ) -> list[MemorySearchResult]:
        """Search supplied documents and optionally fall back to the DB."""

        _ = index_db_path
        root = root or self._root
        resolved_documents = list(documents)
        if not resolved_documents:
            resolved_documents = self._load_documents_from_index(
                filters.user_id,
                relationship_entity_id=filters.relationship_entity_id,
            )
        if not resolved_documents:
            return []
        index_embeddings = _load_embeddings_from_index_db(
            index_db_path, filters.user_id
        )

        query_terms = _query_terms(query)
        resolved_embedding_service = (
            embedding_service
            if isinstance(embedding_service, IEmbeddingService)
            else self._embedding_service
        )
        query_embedding = _resolve_query_embedding(
            query,
            query_embedding=query_embedding,
            embedding_service=resolved_embedding_service,
        )
        results = _search_documents(
            resolved_documents,
            filters=filters,
            query_terms=query_terms,
            query_embedding=query_embedding,
            index_embeddings=index_embeddings,
            limit=limit,
            root=root,
        )
        return results

    def _load_documents_from_index(
        self,
        user_id: str,
        *,
        relationship_entity_id: str | None,
    ) -> list[MemoryIndexDocument]:
        documents = _stored_documents_for_scope(
            self._store,
            user_id=user_id,
            relationship_entity_id=relationship_entity_id,
        )
        return [
            MemoryIndexDocument(
                path=stored.path,
                reference=_relative_reference(stored.path, self._root),
                document=stored.document,
                embedding=[],
            )
            for stored in documents
        ]


def _search_documents(
    documents: Sequence[MemoryIndexDocument],
    *,
    filters: MemorySearchFilters,
    query_terms: list[str],
    query_embedding: list[float],
    index_embeddings: Mapping[str, list[float]],
    limit: int,
    root: Path,
) -> list[MemorySearchResult]:
    results: list[MemorySearchResult] = []
    for index_document in documents:
        front_matter = index_document.document.front_matter
        if not _passes_filters(front_matter, filters):
            continue
        document_embedding = index_document.embedding or index_embeddings.get(
            index_document.reference,
            [],
        )
        indexed_text = _indexed_text(front_matter, index_document.document.body)
        tags_text = " ".join(front_matter_string_list(front_matter.get("tags")))
        matched_terms = _matched_terms(query_terms, [indexed_text, tags_text])

        score = _score_document(
            front_matter,
            terms=query_terms,
            matched_terms=matched_terms,
            indexed_text=indexed_text,
            query_embedding=query_embedding,
            document_embedding=document_embedding,
        )
        if score <= 0.0:
            continue

        source = _source_from_document(index_document, root=root)
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


def _resolve_query_embedding(
    query: str,
    *,
    query_embedding: list[float] | None,
    embedding_service: IEmbeddingService | None,
) -> list[float]:
    if query_embedding is not None:
        return query_embedding
    if embedding_service is not None and query.strip():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                result = asyncio.run(embedding_service.embed_texts([query]))
                if not is_err(result):
                    embeddings = result.value
                    if embeddings:
                        return embeddings[0]
            except RuntimeError:
                pass
    terms = _query_terms(query)
    return embed_text_deterministically(" ".join(terms) if terms else query)


async def embed_memory_index_records(
    documents: Sequence[MemoryMarkdownDocument],
    *,
    embedding_service: IEmbeddingService | None,
) -> list[list[float]]:
    # Imported by memory index maintenance; kept here with index text rendering.
    texts = [
        _indexed_text(document.front_matter, document.body) for document in documents
    ]
    if embedding_service is None:
        return [embed_text_deterministically(text) for text in texts]
    result = await embedding_service.embed_texts(texts)
    if is_err(result) or not result.value:
        return [embed_text_deterministically(text) for text in texts]
    return [list(embedding) for embedding in result.value]


def record_from_memory_index_document(
    index_document: MemoryIndexDocument,
    *,
    embedding: list[float],
) -> MemoryIndexRecord:
    # Imported by memory index maintenance; kept here with index text rendering.
    front_matter = index_document.document.front_matter
    source_path = index_document.reference
    body = index_document.document.body
    rendered = render_memory_markdown(
        front_matter,
        body,
        location=index_document.reference,
    )
    content_hash = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    user_id = front_matter.get("user_id")
    if not isinstance(user_id, str):
        user_id = None
    return MemoryIndexRecord(
        source_path=source_path,
        source_id=front_matter_string(front_matter.get("id")),
        user_id=user_id,
        memory_type=front_matter_string(front_matter.get("memory_type")),
        title=_title(front_matter),
        content_hash=content_hash,
        indexed_text=_indexed_text(front_matter, body),
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
        decay_score=calculate_decay_score(
            front_matter, reference_time=datetime.now(UTC)
        ),
        embedding=embedding,
    )


def _load_embeddings_from_index_db(
    index_db_path: Path | None,
    user_id: str,
) -> dict[str, list[float]]:
    if index_db_path is None or not index_db_path.exists():
        return {}
    try:
        connection = sqlite3.connect(str(index_db_path))
    except sqlite3.Error:
        return {}
    try:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """
            select source_path, embedding
            from memory_index_documents
            where user_id = ?
               or (
                   user_id is null
                   and (
                       source_path = ?
                       or source_path like 'profiles/agent/%'
                   )
               )
            """,
            (user_id, _AGENT_PROFILE_PATH),
        )
        embeddings: dict[str, list[float]] = {}
        for row in cursor.fetchall():
            source_path = str(row["source_path"])
            embeddings[source_path] = _coerce_embedding(row["embedding"])
        return embeddings
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def _stored_documents_for_scope(
    store: FilesystemMemoryStore,
    *,
    user_id: str | None,
    relationship_entity_id: str | None = None,
) -> list[MemoryIndexDocument]:
    documents: list[MemoryIndexDocument] = []
    if user_id is None:
        for agent_profile_path in _agent_profile_paths(store):
            if agent_profile_path.exists():
                documents.append(
                    MemoryIndexDocument(
                        path=agent_profile_path,
                        reference=_relative_reference(agent_profile_path, store.root),
                        document=store.read_document(
                            agent_profile_path,
                            expected_memory_type="profile",
                        ),
                    )
                )
        profiles_root = store.root / "profiles" / "users"
        if profiles_root.exists():
            for path in sorted(profiles_root.glob("*.md")):
                user_scope = unquote(path.stem)
                loaded = store.read_document(
                    path,
                    expected_memory_type="profile",
                    expected_user_id=user_scope,
                )
                documents.append(
                    MemoryIndexDocument(
                        path=path,
                        reference=_relative_reference(path, store.root),
                        document=loaded,
                    )
                )
        for timeline_path in sorted((store.root / "timeline").rglob("*.md")):
            user_scope = _path_segment_after_root(
                store.root / "timeline", timeline_path
            )
            loaded = store.read_document(
                timeline_path,
                expected_memory_type="timeline",
                expected_user_id=user_scope,
            )
            documents.append(
                MemoryIndexDocument(
                    path=timeline_path,
                    reference=_relative_reference(timeline_path, store.root),
                    document=loaded,
                )
            )
        for entity_path in sorted((store.root / "entities").rglob("*.md")):
            user_scope = _path_segment_after_root(store.root / "entities", entity_path)
            loaded = store.read_document(
                entity_path,
                expected_memory_type="entity",
                expected_user_id=user_scope,
            )
            if not _entity_is_selected_relationship(
                loaded.front_matter,
                relationship_entity_id=relationship_entity_id,
            ):
                continue
            documents.append(
                MemoryIndexDocument(
                    path=entity_path,
                    reference=_relative_reference(entity_path, store.root),
                    document=loaded,
                )
            )
        return documents

    for agent_profile_path in _agent_profile_paths(store):
        if agent_profile_path.exists():
            documents.append(
                MemoryIndexDocument(
                    path=agent_profile_path,
                    reference=_relative_reference(agent_profile_path, store.root),
                    document=store.read_document(
                        agent_profile_path,
                        expected_memory_type="profile",
                    ),
                )
            )

    user_profile_path = store.user_profile_path(user_id)
    if user_profile_path.exists():
        documents.append(
            MemoryIndexDocument(
                path=user_profile_path,
                reference=_relative_reference(user_profile_path, store.root),
                document=store.read_document(
                    user_profile_path,
                    expected_memory_type="profile",
                    expected_user_id=user_id,
                ),
            )
        )

    for path in store.iter_timeline_paths(user_id):
        documents.append(
            MemoryIndexDocument(
                path=path,
                reference=_relative_reference(path, store.root),
                document=store.read_document(
                    path,
                    expected_memory_type="timeline",
                    expected_user_id=user_id,
                ),
            )
        )

    for path in store.iter_entity_paths(user_id):
        loaded = store.read_document(
            path,
            expected_memory_type="entity",
            expected_user_id=user_id,
        )
        if not _entity_is_selected_relationship(
            loaded.front_matter,
            relationship_entity_id=relationship_entity_id,
        ):
            continue
        documents.append(
            MemoryIndexDocument(
                path=path,
                reference=_relative_reference(path, store.root),
                document=loaded,
            )
        )
    return documents


def _passes_filters(
    front_matter: Mapping[str, object], filters: MemorySearchFilters
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
        if (
            filters.relationship_entity_id is not None
            and front_matter.get("entity_type") == "relationship"
        ):
            if front_matter.get("id") != filters.relationship_entity_id:
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


def _entity_is_selected_relationship(
    front_matter: Mapping[str, object],
    *,
    relationship_entity_id: str | None,
) -> bool:
    if front_matter.get("entity_type") != "relationship":
        return True
    if relationship_entity_id is None:
        return True
    return front_matter_string(front_matter.get("id")) == relationship_entity_id


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


def _indexed_text(front_matter: Mapping[str, object], body: str) -> str:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        fields = [
            "profile_part",
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
    document_embedding: list[float],
) -> float:
    memory_type = front_matter.get("memory_type")
    importance = _float_value(front_matter.get("importance"), default=0.5)
    confidence = _float_value(front_matter.get("confidence"), default=1.0)
    decay_score = _float_value(front_matter.get("decay_score"), default=1.0)
    score = (0.20 * importance) + (0.15 * confidence) + (0.10 * decay_score)
    if not terms:
        return score if _always_include(front_matter) else 0.0
    searchable_text = indexed_text.lower()
    for term in matched_terms:
        score += 1.0 + min(searchable_text.count(term), 3) * 0.15
    semantic_score = _semantic_score(
        query_embedding,
        indexed_text,
        document_embedding=document_embedding,
    )
    if (
        not matched_terms
        and not document_embedding
        and not _always_include(front_matter)
    ):
        return 0.0
    if (
        not matched_terms
        and semantic_score < _SEMANTIC_FALLBACK_THRESHOLD
        and not _always_include(front_matter)
    ):
        return 0.0
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
        if front_matter.get("timeline_type") in {"daily_summary", "section_summary"}:
            score += 0.25
        elif front_matter.get("timeline_type") == "raw":
            score *= 0.90
    elif memory_type == "profile":
        score *= 0.85
    return score


def _semantic_score(
    query_embedding: list[float],
    indexed_text: str,
    *,
    document_embedding: list[float],
) -> float:
    if not query_embedding:
        return 0.0
    resolved_embedding = document_embedding or embed_text_deterministically(
        indexed_text
    )
    return _cosine_similarity(query_embedding, resolved_embedding)


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


def _source_from_document(
    index_document: MemoryIndexDocument,
    *,
    root: Path,
) -> MemorySource:
    front_matter = index_document.document.front_matter
    memory_type = front_matter_string(front_matter.get("memory_type"))
    return MemorySource(
        id=front_matter_string(front_matter.get("id")),
        memory_type=memory_type,  # type: ignore[arg-type]
        title=_title(front_matter),
        user_id=_source_user_id(front_matter),
        reference=_relative_reference(index_document.path, root),
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
        display_name = front_matter_string_or_none(front_matter.get("display_name"))
        profile_part = front_matter_string_or_none(front_matter.get("profile_part"))
        if display_name and profile_part:
            return f"{display_name} / {profile_part}"
        return display_name or profile_part
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


def _agent_profile_paths(store: FilesystemMemoryStore) -> list[Path]:
    bundle_paths = [
        store.agent_profile_part_path("AGENTS"),
        store.agent_profile_part_path("SOUL"),
        store.agent_profile_part_path("PERSONAL"),
        store.agent_profile_part_path("MEMORY"),
    ]
    if any(path.exists() for path in bundle_paths):
        return bundle_paths

    return []


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


def _relative_reference(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _path_segment_after_root(root: Path, path: Path) -> str:
    return unquote(path.relative_to(root).parts[0])


def _coerce_embedding(value: object) -> list[float]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        value = parsed
    if not isinstance(value, list):
        return []
    embedding: list[float] = []
    for item in value:
        if isinstance(item, (int, float)):
            embedding.append(float(item))
    return embedding
