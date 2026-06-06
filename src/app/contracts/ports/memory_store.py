"""Memory store port."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol


class IMemoryStore(Protocol):
    """Interface for filesystem-backed memory document storage."""

    root: Path

    def agent_profile_dir(self, character_id: str) -> Path:
        """Return the agent profile bundle directory."""
        ...

    def agent_profile_part_path(
        self,
        part: str,
        *,
        character_id: str,
    ) -> Path:
        """Return one agent profile bundle file path."""
        ...

    def agent_profile_bundle_paths(
        self,
        *,
        character_id: str,
    ) -> dict[str, Path]:
        """Return all agent profile bundle paths keyed by part name."""
        ...

    def user_profile_path(self, user_id: str) -> Path:
        """Return a user-scoped profile path."""
        ...

    def entity_path(self, user_id: str, entity_id: str) -> Path:
        """Return a user-scoped entity path."""
        ...

    def raw_timeline_path(
        self,
        *,
        user_id: str,
        occurred_at: datetime,
        role: str,
    ) -> Path:
        """Return a new user-scoped raw timeline path."""
        ...

    def daily_timeline_path(self, *, user_id: str, day: date) -> Path:
        """Return the user-scoped daily summary path."""
        ...

    def section_timeline_path(
        self,
        *,
        user_id: str,
        day: date,
        section_slug: str,
    ) -> Path:
        """Return the user-scoped section summary path."""
        ...

    def iter_timeline_paths(self, user_id: str) -> list[Path]:
        """Return all user-scoped timeline document paths."""
        ...

    def iter_entity_paths(self, user_id: str) -> list[Path]:
        """Return all user-scoped entity document paths."""
        ...

    def read_document(
        self,
        path: Path,
        *,
        expected_memory_type: str | None = None,
        expected_user_id: str | None = None,
    ) -> Any:
        """Read and validate a memory document from storage."""
        ...

    def write_document(
        self,
        path: Path,
        *,
        front_matter: dict[str, object],
        body: str,
    ) -> None:
        """Render and write a memory document to storage."""
        ...


def decode_path_segment(value: str) -> str:
    """Decode a filesystem path segment back to its original identifier."""

    from urllib.parse import unquote

    return unquote(value)
