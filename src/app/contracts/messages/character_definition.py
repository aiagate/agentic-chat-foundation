"""Built-in character definitions and active character selection helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelationshipDefaults:
    """Default relationship values for one character."""

    trust_score: float = 0.0
    warmth_score: float = 0.0
    stage: int = 0


@dataclass(frozen=True, slots=True)
class CharacterDefinition:
    """Stable metadata for one built-in agent character."""

    character_id: str
    display_name: str
    relationship_entity_id: str
    relationship_entity_label: str
    relationship_entity_type: str = "relationship"
    relationship_tag: str = "agent-growth"
    profile_user_id: str = "ai"
    relationship_defaults: RelationshipDefaults = RelationshipDefaults()


CURRENT_CHARACTER = CharacterDefinition(
    character_id="shirasagi-reina",
    display_name="白鷺 レイナ",
    relationship_entity_id="relationship:shirasagi-reina",
    relationship_entity_label="白鷺レイナとの関係",
    relationship_defaults=RelationshipDefaults(
        trust_score=0.0,
        warmth_score=0.0,
        stage=0,
    ),
)

BUILTIN_CHARACTER_DEFINITIONS: dict[str, CharacterDefinition] = {
    CURRENT_CHARACTER.character_id: CURRENT_CHARACTER,
}

DEFAULT_CHARACTER_ID = CURRENT_CHARACTER.character_id
ACTIVE_CHARACTER_ID_ENV_VAR = "ACTIVE_CHARACTER_ID"
LEGACY_CHARACTER_ID_ENV_VAR = "AGENT_CHARACTER_ID"


def selected_character_id() -> str:
    """Return the active character identifier from environment configuration."""

    raw_value = (
        os.getenv(ACTIVE_CHARACTER_ID_ENV_VAR)
        or os.getenv(LEGACY_CHARACTER_ID_ENV_VAR)
        or DEFAULT_CHARACTER_ID
    )
    normalized = raw_value.strip().lower()
    return normalized or DEFAULT_CHARACTER_ID


def resolve_character_definition(
    character_id: str | None = None,
) -> CharacterDefinition:
    """Return a built-in character definition by identifier."""

    resolved_character_id = (
        selected_character_id()
        if character_id is None
        else character_id.strip().lower()
    )
    resolved_character_id = resolved_character_id or DEFAULT_CHARACTER_ID
    try:
        return BUILTIN_CHARACTER_DEFINITIONS[resolved_character_id]
    except KeyError as exc:
        available = ", ".join(sorted(BUILTIN_CHARACTER_DEFINITIONS))
        raise ValueError(
            f"Unknown character_id {resolved_character_id!r}. Available characters: {available}"
        ) from exc


def selected_character_definition() -> CharacterDefinition:
    """Return the active built-in character definition."""

    return resolve_character_definition(selected_character_id())
