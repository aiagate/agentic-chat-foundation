"""Event bus port."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class IEventBus(ABC):
    """Abstract event bus used by application layers."""

    @abstractmethod
    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event to a topic."""
        pass

    @abstractmethod
    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe a handler to a topic."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start listening for events."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening for events."""
        pass
