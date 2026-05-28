"""No-op event bus implementation."""

from __future__ import annotations

from collections.abc import Mapping

from app.contracts.ports.event_bus import EventHandler, IEventBus


class NullEventBus(IEventBus):
    """Event bus implementation that intentionally does nothing."""

    async def publish(self, topic: str, payload: Mapping[str, object]) -> None:
        return None

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None
