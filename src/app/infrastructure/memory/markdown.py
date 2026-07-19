"""Markdown front matter parsing and validation for memory documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import yaml

SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_MEMORY_TYPES = frozenset({"profile", "timeline", "entity"})
FRONT_MATTER_BOUNDARY = "---"

_COMMON_REQUIRED_FIELDS = frozenset(
    {"schema_version", "memory_type", "id", "created_at", "updated_at"}
)
_PROFILE_REQUIRED_FIELDS = frozenset({"profile_scope"})
_TIMELINE_REQUIRED_FIELDS = frozenset(
    {"user_id", "timeline_type", "kind", "content", "occurred_at", "source"}
)
_ENTITY_REQUIRED_FIELDS = frozenset({"user_id", "label", "entity_type"})
_TIMESTAMP_FIELDS_BY_TYPE = {
    "profile": frozenset({"created_at", "updated_at"}),
    "timeline": frozenset({"created_at", "updated_at", "occurred_at"}),
    "entity": frozenset({"created_at", "updated_at"}),
}


class MemoryMarkdownError(ValueError):
    """Raised when a memory Markdown document cannot be parsed or validated."""


@dataclass(frozen=True, slots=True)
class MemoryMarkdownDocument:
    """Parsed Markdown memory document."""

    front_matter: dict[str, object]
    body: str


def parse_memory_markdown(
    text: str,
    *,
    location: str = "<memory document>",
) -> MemoryMarkdownDocument:
    """Parse and validate a Markdown document with YAML front matter."""

    front_matter, body = _split_front_matter(text, location=location)
    validate_front_matter(front_matter, location=location)
    return MemoryMarkdownDocument(front_matter=front_matter, body=body)


def render_memory_markdown(
    front_matter: dict[str, object],
    body: str,
    *,
    location: str = "<memory document>",
) -> str:
    """Render validated front matter and Markdown body into a document."""

    validate_front_matter(front_matter, location=location)
    yaml_text = yaml.safe_dump(
        front_matter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    normalized_body = body.rstrip()
    return (
        f"{FRONT_MATTER_BOUNDARY}\n"
        f"{yaml_text}\n"
        f"{FRONT_MATTER_BOUNDARY}\n\n"
        f"{normalized_body}\n"
    )


def validate_front_matter(
    front_matter: dict[str, object],
    *,
    location: str = "<memory document>",
) -> None:
    """Validate schema version, memory type, and required fields."""

    _require_fields(front_matter, _COMMON_REQUIRED_FIELDS, location=location)

    schema_version = front_matter["schema_version"]
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise MemoryMarkdownError(
            f"{location}: unsupported schema_version {schema_version!r}"
        )

    memory_type = front_matter["memory_type"]
    if not isinstance(memory_type, str) or memory_type not in SUPPORTED_MEMORY_TYPES:
        raise MemoryMarkdownError(f"{location}: invalid memory_type {memory_type!r}")

    if memory_type == "profile":
        _validate_profile_front_matter(front_matter, location=location)
    elif memory_type == "timeline":
        _require_fields(front_matter, _TIMELINE_REQUIRED_FIELDS, location=location)
    elif memory_type == "entity":
        _require_fields(front_matter, _ENTITY_REQUIRED_FIELDS, location=location)

    for field_name in _TIMESTAMP_FIELDS_BY_TYPE[memory_type]:
        _validate_iso_timestamp(front_matter[field_name], field_name, location=location)


def _split_front_matter(
    text: str,
    *,
    location: str,
) -> tuple[dict[str, object], str]:
    stripped = text.lstrip()
    if not stripped.startswith(f"{FRONT_MATTER_BOUNDARY}\n"):
        raise MemoryMarkdownError(f"{location}: missing YAML front matter")

    remainder = stripped[len(FRONT_MATTER_BOUNDARY) + 1 :]
    terminator = f"\n{FRONT_MATTER_BOUNDARY}\n"
    terminator_index = remainder.find(terminator)
    if terminator_index == -1:
        raise MemoryMarkdownError(f"{location}: missing YAML front matter terminator")

    yaml_text = remainder[:terminator_index]
    body = remainder[terminator_index + len(terminator) :]
    try:
        loaded = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise MemoryMarkdownError(f"{location}: invalid YAML front matter") from exc

    if not isinstance(loaded, dict):
        raise MemoryMarkdownError(f"{location}: expected YAML mapping in front matter")
    return cast(dict[str, object], loaded), body


def _require_fields(
    front_matter: dict[str, object],
    required_fields: frozenset[str],
    *,
    location: str,
) -> None:
    missing = [
        field_name
        for field_name in sorted(required_fields)
        if field_name not in front_matter or front_matter[field_name] is None
    ]
    if missing:
        joined = ", ".join(missing)
        raise MemoryMarkdownError(f"{location}: missing required fields: {joined}")


def _validate_profile_front_matter(
    front_matter: dict[str, object],
    *,
    location: str,
) -> None:
    _require_fields(front_matter, _PROFILE_REQUIRED_FIELDS, location=location)
    profile_scope = front_matter["profile_scope"]
    if profile_scope != "user":
        raise MemoryMarkdownError(
            f"{location}: invalid profile_scope {profile_scope!r}"
        )
    user_id = front_matter.get("user_id")
    if not isinstance(user_id, str):
        raise MemoryMarkdownError(f"{location}: user profile requires user_id")


def _validate_iso_timestamp(
    value: object,
    field_name: str,
    *,
    location: str,
) -> None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise MemoryMarkdownError(
                f"{location}: {field_name} must be timezone-aware"
            )
        return
    if not isinstance(value, str):
        raise MemoryMarkdownError(f"{location}: {field_name} must be an ISO string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MemoryMarkdownError(
            f"{location}: {field_name} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise MemoryMarkdownError(f"{location}: {field_name} must be timezone-aware")


def front_matter_string(value: object, *, default: str = "") -> str:
    """Return a front matter value as a string for DTO conversion."""

    if value is None:
        return default
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def front_matter_string_or_none(value: object) -> str | None:
    """Return a front matter value as a nullable string for DTO conversion."""

    if value is None:
        return None
    return front_matter_string(value)


def front_matter_string_list(value: object) -> list[str]:
    """Return a front matter value as a string list for DTO conversion."""

    if not isinstance(value, list):
        return []
    return [front_matter_string(item) for item in value]


def front_matter_string_dict(value: object) -> dict[str, str]:
    """Return a front matter value as a string dictionary for DTO conversion."""

    if not isinstance(value, dict):
        return {}
    return {str(key): front_matter_string(item) for key, item in value.items()}


def front_matter_float(value: object, *, default: float) -> float:
    """Return a front matter value as a float for DTO conversion."""

    if value is None:
        return default
    return float(cast(Any, value))
