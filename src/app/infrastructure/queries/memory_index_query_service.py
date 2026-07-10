"""Memory index search service."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from flow_res import is_err

from app.contracts.messages.memory_context import MemorySearchHit, MemorySource
from app.contracts.messages.memory_index import (
    MemoryIndexDocument,
    MemorySearchFilters,
    MemorySearchResult,
)
from app.contracts.ports.embedding_service import IEmbeddingService
from app.infrastructure.memory.embedding import (
    embed_text_deterministically,
)
from app.infrastructure.memory.index_projection import indexed_text
from app.infrastructure.memory.markdown import (
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
)

_TERM_PATTERN = re.compile(r"[\w一-龯ぁ-んァ-ヶー]+", re.UNICODE)
_SEMANTIC_FALLBACK_THRESHOLD = 0.55


class MemoryIndexSearch:
    """Rank memory documents already loaded from the main DB projection."""

    def __init__(
        self,
        embedding_service: IEmbeddingService | None = None,
    ) -> None:
        self._embedding_service = embedding_service

    def search_memory_index(
        self,
        query: str,
        documents: Sequence[MemoryIndexDocument],
        filters: MemorySearchFilters,
        *,
        root: Path | None = None,
        embedding_service: object | None = None,
        query_embedding: list[float] | None = None,
        limit: int = 20,
    ) -> list[MemorySearchResult]:
        """Search documents loaded through ``IMemoryIndexQuery``."""

        root = root or Path(".")
        if not documents:
            return []

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
            documents,
            filters=filters,
            query_terms=query_terms,
            query_embedding=query_embedding,
            limit=limit,
            root=root,
        )
        return results


def _search_documents(
    documents: Sequence[MemoryIndexDocument],
    *,
    filters: MemorySearchFilters,
    query_terms: list[str],
    query_embedding: list[float],
    limit: int,
    root: Path,
) -> list[MemorySearchResult]:
    results: list[MemorySearchResult] = []
    for index_document in documents:
        front_matter = index_document.document.front_matter
        if not _passes_filters(front_matter, filters):
            continue
        document_embedding = index_document.embedding
        searchable_text = indexed_text(front_matter, index_document.document.body)
        tags_text = " ".join(front_matter_string_list(front_matter.get("tags")))
        matched_terms = _matched_terms(query_terms, [searchable_text, tags_text])

        score = _score_document(
            front_matter,
            terms=query_terms,
            matched_terms=matched_terms,
            indexed_text=searchable_text,
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
        title=_title(front_matter, reference=index_document.reference),
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


def _title(
    front_matter: Mapping[str, object],
    *,
    reference: str | None,
) -> str | None:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        if reference:
            return Path(reference).stem
    if memory_type == "entity":
        return front_matter_string_or_none(front_matter.get("label"))
    if memory_type == "timeline":
        return front_matter_string_or_none(front_matter.get("kind"))
    return None


def _excerpt(front_matter: Mapping[str, object], body: str) -> str:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        text = body
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
