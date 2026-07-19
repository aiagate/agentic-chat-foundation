"""User identity aggregate for conversation ownership."""

from __future__ import annotations

from dataclasses import dataclass

from ulid import ULID


@dataclass(frozen=True, slots=True)
class UserChannelIdentity:
    """One provider identity owned by a user."""

    channel: str
    external_participant_id: str

    def __post_init__(self) -> None:
        channel = self.channel.strip().lower()
        participant_id = self.external_participant_id.strip()
        if channel not in {"discord", "line"}:
            raise ValueError(f"Unsupported user identity channel: {self.channel}")
        if not participant_id:
            raise ValueError("External participant id cannot be empty")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "external_participant_id", participant_id)


@dataclass(frozen=True, slots=True)
class User:
    """Conversation owner shared by one or more channel identities."""

    id: str
    identities: tuple[UserChannelIdentity, ...]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("User id must not be empty")
        try:
            ULID.from_str(self.id)
        except ValueError as exc:
            raise ValueError("User id must be a valid ULID") from exc
        if not self.identities:
            raise ValueError("User must have at least one channel identity")
        if len(set(self.identities)) != len(self.identities):
            raise ValueError("User channel identities must be unique")
