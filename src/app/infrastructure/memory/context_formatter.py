"""Helpers for rendering compact and detailed memory context."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from app.contracts.messages.memory_context import (
    MemoryManifestItem,
    MemoryReadResult,
    MemorySource,
)
from app.contracts.messages.memory_index import MemoryIndexDocument
from app.infrastructure.memory.markdown import (
    front_matter_string,
    front_matter_string_list,
    front_matter_string_or_none,
)


def manifest_item_from_document(
    index_document: MemoryIndexDocument,
) -> MemoryManifestItem:
    """Build the compact manifest entry used for agent prompt context."""

    front_matter = index_document.document.front_matter
    memory_type = front_matter_string(front_matter.get("memory_type"))
    return MemoryManifestItem(
        memory_id=memory_id_for_document(index_document),
        memory_type=memory_type,  # type: ignore[arg-type]
        when=manifest_when(front_matter),
        title=manifest_title(index_document),
        summary=manifest_summary(index_document),
        tags=front_matter_string_list(front_matter.get("tags")),
        updated_at=front_matter_string_or_none(front_matter.get("updated_at")),
    )


def memory_read_result_from_document(
    index_document: MemoryIndexDocument,
    manifest_item: MemoryManifestItem,
) -> MemoryReadResult:
    """Build the detailed memory read payload for tool responses."""

    front_matter = index_document.document.front_matter
    return MemoryReadResult(
        memory_id=manifest_item.memory_id,
        source=MemorySource(
            id=front_matter_string(
                front_matter.get("id"), default=manifest_item.memory_id
            ),
            memory_type=front_matter_string(front_matter.get("memory_type")),  # type: ignore[arg-type]
            title=manifest_item.title,
            user_id=source_user_id(front_matter),
            reference=index_document.reference,
        ),
        title=manifest_item.title,
        summary=manifest_item.summary,
        rendered_text=render_memory_detail(index_document, manifest_item),
    )


def render_manifest_context(
    items: list[MemoryManifestItem],
    *,
    max_chars: int = 6_000,
) -> str:
    """Render the compact manifest block inserted into the agent prompt."""

    lines = [
        "Memory manifest:",
        "Use memory.read with a memory_id when detailed memory is needed.",
    ]
    for item in items:
        line = render_manifest_item(item)
        candidate = "\n".join([*lines, line])
        if len(candidate) > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)


def render_manifest_item(item: MemoryManifestItem) -> str:
    """Render one compact manifest line."""

    if item.memory_type == "timeline":
        when = item.when or "unknown"
        return (
            f"- {item.memory_id} | when={when} | {item.memory_type} | "
            f"{item.title} | {item.summary}"
        )
    return f"- {item.memory_id} | {item.memory_type} | {item.title} | {item.summary}"


def render_memory_detail(
    index_document: MemoryIndexDocument,
    manifest_item: MemoryManifestItem,
) -> str:
    """Render one detailed memory payload."""

    front_matter = index_document.document.front_matter
    body = index_document.document.body.strip()
    lines = [
        f"## Memory: {manifest_item.memory_id}",
        f"- memory_type: {manifest_item.memory_type}",
        f"- title: {manifest_item.title}",
        f"- summary: {manifest_item.summary}",
    ]
    if manifest_item.tags:
        lines.append(f"- tags: {', '.join(manifest_item.tags)}")
    if manifest_item.updated_at is not None:
        lines.append(f"- updated_at: {manifest_item.updated_at}")
    if index_document.reference:
        lines.append(f"- reference: {index_document.reference}")
    memory_type = front_matter.get("memory_type")
    if memory_type == "entity":
        lines.extend(_entity_detail_lines(front_matter))
    elif memory_type == "timeline":
        lines.extend(_timeline_detail_lines(front_matter))
    elif memory_type == "profile":
        lines.extend(_profile_detail_lines(front_matter))
    if body:
        lines.extend(["", body])
    return "\n".join(lines).strip()


def memory_id_for_document(index_document: MemoryIndexDocument) -> str:
    """Resolve the stable memory_id used by the tool surface."""

    front_matter = index_document.document.front_matter
    explicit_memory_id = front_matter_string_or_none(front_matter.get("memory_id"))
    if explicit_memory_id:
        return explicit_memory_id
    memory_type = front_matter.get("memory_type")
    reference = index_document.reference
    if memory_type == "profile":
        if front_matter.get("profile_scope") == "agent":
            return f"agent_profile:{Path(reference).stem.lower()}"
        user_id = front_matter_string(front_matter.get("user_id"), default="unknown")
        return f"profile:{quote(user_id, safe='')}"
    raw_id = front_matter_string(front_matter.get("id"))
    return f"{memory_type}:{quote(raw_id, safe=':_-')}"


def manifest_title(index_document: MemoryIndexDocument) -> str:
    """Resolve the compact title used in memory manifest lines."""

    front_matter = index_document.document.front_matter
    explicit_title = front_matter_string_or_none(front_matter.get("manifest_title"))
    if explicit_title:
        return explicit_title
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        display_name = front_matter_string_or_none(front_matter.get("display_name"))
        return display_name or Path(index_document.reference).stem
    if memory_type == "entity":
        return front_matter_string(front_matter.get("label"))
    if memory_type == "timeline":
        content = front_matter_string(front_matter.get("content"))
        if content:
            return _one_line_excerpt(content, limit=48)
        return front_matter_string(front_matter.get("kind"), default="timeline")
    return front_matter_string(front_matter.get("id"), default="memory")


def manifest_summary(index_document: MemoryIndexDocument) -> str:
    """Resolve the compact summary used in memory manifest lines."""

    front_matter = index_document.document.front_matter
    explicit_summary = front_matter_string_or_none(front_matter.get("manifest_summary"))
    if explicit_summary:
        return explicit_summary
    memory_type = front_matter.get("memory_type")
    if memory_type == "profile":
        summary = front_matter_string(front_matter.get("summary"))
        if summary:
            return _one_line_excerpt(summary)
        return _one_line_excerpt(index_document.document.body)
    if memory_type == "timeline":
        content = front_matter_string(front_matter.get("content"))
        return _one_line_excerpt(content or index_document.document.body)
    if memory_type == "entity":
        label = front_matter_string(front_matter.get("label"))
        entity_type = front_matter_string(front_matter.get("entity_type"))
        status = front_matter_string(front_matter.get("status"), default="active")
        missing_attributes = front_matter_string_list(
            front_matter.get("missing_attributes")
        )
        parts = [label, entity_type, status]
        if missing_attributes:
            parts.append(f"missing: {', '.join(missing_attributes)}")
        return _one_line_excerpt(" | ".join(part for part in parts if part))
    return _one_line_excerpt(index_document.document.body)


def manifest_when(front_matter: dict[str, object]) -> str | None:
    """Resolve the date-like `when` field for timeline manifest entries."""

    if front_matter.get("memory_type") != "timeline":
        return None
    occurred_at = front_matter_string_or_none(front_matter.get("occurred_at"))
    if occurred_at is None:
        return None
    date_part = occurred_at.split("T", maxsplit=1)[0].strip()
    return date_part or occurred_at


def source_user_id(front_matter: dict[str, object]) -> str | None:
    """Resolve the user scope for rendered memory sources."""

    if front_matter.get("profile_scope") == "agent":
        return None
    value = front_matter.get("user_id")
    if isinstance(value, str):
        return value
    return None


def _profile_detail_lines(front_matter: dict[str, object]) -> list[str]:
    lines: list[str] = []
    display_name = front_matter_string_or_none(front_matter.get("display_name"))
    if display_name is not None:
        lines.append(f"- display_name: {display_name}")
    summary = front_matter_string(front_matter.get("summary"))
    if summary:
        lines.append(f"- profile_summary: {summary}")
    traits = front_matter_string_list(front_matter.get("traits"))
    if traits:
        lines.append(f"- traits: {', '.join(traits)}")
    preferences = front_matter_string_list(front_matter.get("preferences"))
    if preferences:
        lines.append(f"- preferences: {', '.join(preferences)}")
    return lines


def _timeline_detail_lines(front_matter: dict[str, object]) -> list[str]:
    lines = [
        f"- kind: {front_matter_string(front_matter.get('kind'))}",
        f"- occurred_at: {front_matter_string(front_matter.get('occurred_at'))}",
        f"- source: {front_matter_string(front_matter.get('source'))}",
    ]
    content = front_matter_string(front_matter.get("content"))
    if content:
        lines.append(f"- content: {content}")
    entity_ids = front_matter_string_list(front_matter.get("entity_ids"))
    if entity_ids:
        lines.append(f"- entity_ids: {', '.join(entity_ids)}")
    return lines


def _entity_detail_lines(front_matter: dict[str, object]) -> list[str]:
    lines = [
        f"- id: {front_matter_string(front_matter.get('id'))}",
        f"- label: {front_matter_string(front_matter.get('label'))}",
        f"- entity_type: {front_matter_string(front_matter.get('entity_type'))}",
        f"- status: {front_matter_string(front_matter.get('status'), default='active')}",
    ]
    aliases = front_matter_string_list(front_matter.get("aliases"))
    if aliases:
        lines.append(f"- aliases: {', '.join(aliases)}")
    properties = front_matter.get("properties") or front_matter.get("attributes")
    if isinstance(properties, dict) and properties:
        lines.append("- properties:")
        for key, value in sorted(properties.items()):
            lines.append(f"  - {key}: {_stringify_property_value(value)}")
    missing_attributes = front_matter_string_list(
        front_matter.get("missing_attributes")
    )
    if missing_attributes:
        lines.append(f"- missing_attributes: {', '.join(missing_attributes)}")
    return lines


def _one_line_excerpt(value: str, *, limit: int = 96) -> str:
    compact = " ".join(
        line.strip("#*- ").strip() for line in value.splitlines() if line.strip()
    ).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _stringify_property_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is None:
        return "null"
    return str(value)
