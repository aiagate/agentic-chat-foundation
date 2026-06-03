"""Filesystem-backed memory write service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flow_res import Err, Ok, Result

from app.contracts.messages.memory_context import MemoryEntity, MemoryProfile
from app.contracts.ports.memory_write_service import (
    IMemoryWriteService,
    MemoryWriteServiceError,
)
from app.infrastructure.memory.markdown import MemoryMarkdownError
from app.infrastructure.memory.store import (
    FilesystemMemoryStore,
    MemoryStoreError,
    default_memory_root,
    utc_now_iso,
)


class FilesystemMemoryWriteService(IMemoryWriteService):
    """Adapter that writes memory documents to the local filesystem."""

    def __init__(
        self,
        root: Path | None = None,
        store: FilesystemMemoryStore | None = None,
    ) -> None:
        self._store = store or FilesystemMemoryStore(root or default_memory_root())

    def write_profile(self, profile: MemoryProfile) -> None:
        """Persist a profile memory as Markdown."""

        now = utc_now_iso()
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

    async def add_log(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, str],
    ) -> Result[None, MemoryWriteServiceError]:
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
            return Err(MemoryWriteServiceError(str(exc)))
        return Ok(None)


def _profile_front_matter(
    profile: MemoryProfile,
    *,
    created_at: str,
    updated_at: str,
    profile_scope: str,
    include_content_fields: bool = True,
) -> dict[str, object]:
    user_id: str | None = profile.user_id if profile_scope == "user" else None
    profile_id = f"profile:{profile.user_id}" if profile_scope == "user" else "agent"
    front_matter: dict[str, object] = {
        "schema_version": 1,
        "memory_type": "profile",
        "id": profile_id,
        "user_id": user_id,
        "profile_scope": profile_scope,
        "display_name": profile.display_name,
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": ["profile"],
        "importance": 0.8,
        "confidence": 1.0,
        "pinned": profile_scope == "agent",
        "metadata": {},
    }
    if include_content_fields:
        front_matter["summary"] = profile.summary
        front_matter["traits"] = profile.traits
        front_matter["preferences"] = profile.preferences
        front_matter["communication_style"] = []
        front_matter["known_constraints"] = []
    return front_matter


def _user_profile_body(profile: MemoryProfile) -> str:
    lines = [
        f"# {profile.display_name or profile.user_id}",
        "",
        "## Summary",
        "",
        profile.summary or "",
        "",
        "## Traits",
        "",
    ]
    lines.extend(f"- {trait}" for trait in profile.traits)
    lines.extend(["", "## Preferences", ""])
    lines.extend(f"- {preference}" for preference in profile.preferences)
    return "\n".join(lines)


def _timeline_body(role: str, content: str, metadata: dict[str, str]) -> str:
    lines = [
        "# Raw timeline entry",
        "",
        f"- role: {role}",
        f"- content: {content}",
    ]
    if metadata:
        lines.append("")
        lines.append("## Metadata")
        lines.extend(f"- {key}: {value}" for key, value in metadata.items())
    return "\n".join(lines)
