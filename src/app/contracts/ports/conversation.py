"""Ports for the channel-independent conversation flow."""

from __future__ import annotations

from typing import Protocol

from app.contracts.messages.conversation import (
    AcceptedMessage,
    ConversationResult,
    DeliveryResult,
    IncomingMessage,
)


class ConversationHistory(Protocol):
    """Canonical raw conversation history store."""

    async def append(self, message: IncomingMessage) -> AcceptedMessage:
        """Record an incoming message and return its canonical identity."""
        ...

    async def append_assistant(
        self,
        message: AcceptedMessage,
        result: ConversationResult,
    ) -> None:
        """Record an assistant result after it has been delivered."""
        ...


class ConversationContext(Protocol):
    """Read history and long-term memory needed to answer a message."""

    async def load(self, message: AcceptedMessage) -> object:
        """Load the response context for the accepted message."""
        ...


class ResponseGenerator(Protocol):
    """Generate one logical response from a message and its context."""

    async def generate(
        self, message: AcceptedMessage, context: object
    ) -> ConversationResult:
        """Return a response or an unavailable result."""
        ...


class ConversationResultSender(Protocol):
    """Send a result through the originating channel adapter."""

    async def send(self, result: ConversationResult) -> DeliveryResult:
        """Deliver the result and return the immediate outcome."""
        ...
