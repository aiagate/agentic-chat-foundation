"""Filesystem path and document I/O for Markdown memory storage."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

from app.infrastructure.memory.markdown import (
    MemoryMarkdownDocument,
    MemoryMarkdownError,
    parse_memory_markdown,
    render_memory_markdown,
)

_SAFE_SEGMENT_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)
_AGENT_PROFILE_PARTS: tuple[str, ...] = ("AGENTS", "SOUL", "PERSONAL", "MEMORY")
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)


class MemoryStoreError(OSError):
    """Raised when memory documents cannot be read from or written to storage."""


@dataclass(frozen=True, slots=True)
class StoredMemoryDocument:
    """Parsed memory document and its storage path."""

    path: Path
    document: MemoryMarkdownDocument


def default_memory_root() -> Path:
    """Return the configured memory root path."""

    return Path(os.getenv("MEMORY_ROOT") or os.getenv("MEMORY_AGENT_ROOT") or "memory")


def encode_path_segment(value: str) -> str:
    """Encode an ID into a deterministic, safe filesystem path segment."""

    encoded = quote(value, safe=_SAFE_SEGMENT_CHARS)
    if encoded in {"", ".", ".."}:
        raise MemoryStoreError(f"Invalid memory path segment: {value!r}")
    if encoded.upper() in _WINDOWS_RESERVED_NAMES:
        encoded = f"%{encoded[0].encode('utf-8').hex().upper()}{encoded[1:]}"
    return encoded


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""

    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class FilesystemMemoryStore:
    """Read and write Markdown memory documents under a configured root."""

    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for relative in ("profiles/agent", "profiles/users", "timeline", "entities"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def agent_profile_dir(self, character_id: str) -> Path:
        """Return the agent profile bundle directory."""

        return self.root / "profiles" / "agent" / encode_path_segment(character_id)

    def agent_profile_part_path(
        self,
        part: str,
        *,
        character_id: str,
    ) -> Path:
        """Return one agent profile bundle file path."""

        normalized = part.upper()
        if normalized not in _AGENT_PROFILE_PARTS:
            raise MemoryStoreError(f"Invalid agent profile part: {part!r}")
        return self.agent_profile_dir(character_id) / f"{normalized}.md"

    def agent_profile_bundle_paths(
        self,
        *,
        character_id: str,
    ) -> dict[str, Path]:
        """Return all agent profile bundle paths keyed by part name."""

        return {
            part: self.agent_profile_part_path(part, character_id=character_id)
            for part in _AGENT_PROFILE_PARTS
        }

    def user_profile_path(self, user_id: str) -> Path:
        """Return a user-scoped profile path."""

        return self.root / "profiles" / "users" / f"{encode_path_segment(user_id)}.md"

    def entity_path(self, user_id: str, entity_id: str) -> Path:
        """Return a user-scoped Entity path."""

        return (
            self.root
            / "entities"
            / encode_path_segment(user_id)
            / f"{encode_path_segment(entity_id)}.md"
        )

    def raw_timeline_path(
        self,
        *,
        user_id: str,
        occurred_at: datetime,
        role: str,
    ) -> Path:
        """Return a new user-scoped raw Timeline path."""

        safe_role = encode_path_segment(role.lower())
        return (
            self.root
            / "timeline"
            / encode_path_segment(user_id)
            / "raw"
            / f"{occurred_at:%Y}"
            / f"{occurred_at:%m}"
            / f"{occurred_at:%Y-%m-%d}_{safe_role}-{uuid.uuid4().hex[:8]}.md"
        )

    def daily_timeline_path(self, *, user_id: str, day: date) -> Path:
        """Return the user-scoped daily Timeline summary path."""

        return (
            self.root
            / "timeline"
            / encode_path_segment(user_id)
            / "daily"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%Y-%m-%d}.md"
        )

    def section_timeline_path(
        self,
        *,
        user_id: str,
        day: date,
        section_slug: str,
    ) -> Path:
        """Return the user-scoped section Timeline summary path."""

        safe_slug = encode_path_segment(section_slug)
        return (
            self.root
            / "timeline"
            / encode_path_segment(user_id)
            / "sections"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%Y-%m-%d}_{safe_slug}.md"
        )

    def read_document(
        self,
        path: Path,
        *,
        expected_memory_type: str | None = None,
        expected_user_id: str | None = None,
    ) -> MemoryMarkdownDocument:
        """Read, parse, and validate a Markdown memory document."""

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MemoryStoreError(f"{path}: failed to read memory document") from exc

        try:
            document = parse_memory_markdown(text, location=str(path))
        except MemoryMarkdownError:
            raise

        front_matter = document.front_matter
        memory_type = front_matter["memory_type"]
        if expected_memory_type is not None and memory_type != expected_memory_type:
            raise MemoryMarkdownError(
                f"{path}: expected memory_type {expected_memory_type!r}, "
                f"got {memory_type!r}"
            )
        if (
            expected_user_id is not None
            and front_matter.get("user_id") != expected_user_id
        ):
            raise MemoryMarkdownError(
                f"{path}: path scope and front matter user_id disagree"
            )
        return document

    def write_document(
        self,
        path: Path,
        *,
        front_matter: dict[str, object],
        body: str,
    ) -> None:
        """Render and write a Markdown memory document."""

        try:
            text = render_memory_markdown(front_matter, body, location=str(path))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except MemoryMarkdownError:
            raise
        except OSError as exc:
            raise MemoryStoreError(f"{path}: failed to write memory document") from exc

    def iter_timeline_paths(self, user_id: str) -> list[Path]:
        """Return user-scoped Timeline document paths."""

        base = self.root / "timeline" / encode_path_segment(user_id)
        if not base.exists():
            return []
        return sorted(base.rglob("*.md"))

    def iter_entity_paths(self, user_id: str) -> list[Path]:
        """Return user-scoped Entity document paths."""

        base = self.root / "entities" / encode_path_segment(user_id)
        if not base.exists():
            return []
        return sorted(base.rglob("*.md"))
