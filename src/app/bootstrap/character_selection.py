"""Active character selection for application bootstrap."""

from __future__ import annotations

import os

DEFAULT_CHARACTER_ID = "shirasagi-reina"
ACTIVE_CHARACTER_ID_ENV_VAR = "ACTIVE_CHARACTER_ID"


def resolve_active_character_id() -> str:
    """Return the active character identifier from environment configuration."""

    raw_value = os.getenv(ACTIVE_CHARACTER_ID_ENV_VAR) or DEFAULT_CHARACTER_ID
    normalized = raw_value.strip().lower()
    return normalized or DEFAULT_CHARACTER_ID
