"""Channel-independent messages used by the conversation use cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """Text received from an external conversation channel."""

    channel: str
    external_conversation_id: str
    external_participant_id: str
    text: str
    external_message_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcceptedMessage:
    """Canonical message after it has been recorded in conversation history."""

    message_id: str
    conversation_id: str
    participant_id: str
    text: str
    channel: str
    occurred_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)
    is_new: bool = True


@dataclass(frozen=True, slots=True)
class ConversationResult:
    """Logical response produced for one accepted message."""

    message_id: str
    conversation_id: str
    channel: str
    contents: tuple[str, ...] = ()
    unavailable: bool = False
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Outcome of sending a conversation result to its originating channel."""

    message_id: str
    delivered: bool
    failure_reason: str | None = None
