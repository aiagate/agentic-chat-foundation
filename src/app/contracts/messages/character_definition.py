"""Stable metadata for one built-in agent character."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterDefinition:
    """Stable metadata for one built-in agent character."""

    character_id: str
    profile_user_id: str = "ai"
