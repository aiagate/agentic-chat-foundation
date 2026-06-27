"""Shared chat platform type used across application layers."""

from __future__ import annotations

from enum import StrEnum

from flow_res import Err, Ok, Result


class ChatType(StrEnum):
    """Chat platform type."""

    DISCORD = "DISCORD"
    LINE = "LINE"

    @classmethod
    def from_primitive(cls, value: str) -> Result[ChatType, ValueError]:
        """Restore a chat type from a string value."""

        try:
            normalized = value.strip()
            if not normalized:
                return Err(ValueError("Chat type cannot be empty."))
            return Ok(cls(normalized.upper()))
        except ValueError:
            return Err(ValueError(f"Invalid chat type: {value}"))

    def to_primitive(self) -> str:
        """Return the persistence-friendly string representation."""

        return self.value
