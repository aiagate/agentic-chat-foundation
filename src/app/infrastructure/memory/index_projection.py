"""Build the main DB memory-index projection from Markdown sources."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from flow_res import is_err

from app.contracts.messages.memory_index import MemoryIndexDocument, MemoryIndexRecord
from app.contracts.ports.embedding_service import IEmbeddingService
from app.infrastructure.memory.decay import calculate_decay_score
from app.infrastructure.memory.embedding import embed_text_deterministically
from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
    render_memory_markdown,
)


async def embed_memory_index_records(
    documents: Sequence[MemoryMarkdownDocument],
    *,
    embedding_service: IEmbeddingService | None,
) -> list[list[float]]:
    """Create embeddings for projection records with a deterministic fallback."""

    texts = [
        indexed_text(document.front_matter, document.body) for document in documents
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
    """Convert one Markdown document into a persisted projection record."""

    front_matter = index_document.document.front_matter
    body = index_document.document.body
    rendered = render_memory_markdown(
        front_matter,
        body,
        location=index_document.reference,
    )
    user_id = front_matter_string(front_matter["user_id"])
    return MemoryIndexRecord(
        source_path=index_document.reference,
        source_id=front_matter_string(front_matter.get("id")),
        user_id=user_id,
        memory_type=front_matter_string(front_matter.get("memory_type")),
        title=_title(front_matter, reference=index_document.reference),
        content_hash=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        indexed_text=indexed_text(front_matter, body),
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
            front_matter,
            reference_time=datetime.now(UTC),
        ),
        embedding=embedding,
    )


def indexed_text(front_matter: Mapping[str, object], body: str) -> str:
    """Render the searchable text persisted in the projection."""

    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        fields = ["tags"]
    elif memory_type == "timeline":
        fields = ["content", "kind", "source", "entity_ids", "tags", "metadata"]
    else:
        fields = [
            "label",
            "entity_type",
            "status",
            "aliases",
            "properties",
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


def _title(
    front_matter: Mapping[str, object],
    *,
    reference: str,
) -> str | None:
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        return reference.rsplit("/", maxsplit=1)[-1].removesuffix(".md")
    if memory_type == "entity":
        return front_matter_string_or_none(front_matter.get("label"))
    if memory_type == "timeline":
        return front_matter_string_or_none(front_matter.get("kind"))
    return None


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(
            part for key, item in value.items() for part in (str(key), _stringify(item))
        )
    if isinstance(value, list):
        return " ".join(_stringify(item) for item in value)
    return str(value)


def _float_value(value: object, *, default: float) -> float:
    if value is None or not isinstance(value, str | int | float):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 0.0), 1.0)
