"""Tests for the Redis event bus adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest

from app.infrastructure.messaging.redis_event_bus import RedisEventBus


@pytest.mark.anyio
async def test_redis_event_bus_publish_requires_start() -> None:
    """Publishing before start should fail instead of silently dropping events."""

    bus = RedisEventBus()

    with pytest.raises(RuntimeError):
        await bus.publish("chat.tool.requested", {"tool_call_id": "tool-1"})


@pytest.mark.anyio
async def test_redis_event_bus_publish_serializes_topic_and_payload() -> None:
    """Publish should preserve the topic and payload in the Redis message body."""

    class RedisStub:
        def __init__(self) -> None:
            self.published: list[tuple[str, str]] = []

        async def publish(self, topic: str, payload: str) -> None:
            self.published.append((topic, payload))

    bus = RedisEventBus()
    redis_stub = RedisStub()
    cast(Any, bus)._redis = redis_stub

    await bus.publish("chat.tool.requested", {"tool_call_id": "tool-1"})

    assert redis_stub.published == [
        (
            "chat.tool.requested",
            json.dumps(
                {
                    "topic": "chat.tool.requested",
                    "payload": {"tool_call_id": "tool-1"},
                }
            ),
        )
    ]


@pytest.mark.anyio
async def test_redis_event_bus_process_message_dispatches_topic() -> None:
    """Redis messages should dispatch to handlers registered by exact topic."""

    received: list[dict[str, object]] = []
    bus = RedisEventBus()

    async def handler(payload: Mapping[str, object]) -> None:
        received.append(dict(payload))

    await bus.subscribe("chat.tool.requested", handler)
    await cast(Any, bus)._process_message(
        {
            "type": "message",
            "data": json.dumps(
                {
                    "topic": "chat.tool.requested",
                    "payload": {"tool_call_id": "tool-1"},
                }
            ),
        }
    )

    assert received == [{"tool_call_id": "tool-1"}]


@pytest.mark.anyio
async def test_redis_event_bus_process_pattern_message_dispatches_pattern() -> None:
    """Pattern subscriptions should receive messages through their pattern key."""

    received: list[dict[str, object]] = []
    bus = RedisEventBus()

    async def handler(payload: Mapping[str, object]) -> None:
        received.append(dict(payload))

    await bus.subscribe("chat.*", handler)
    await cast(Any, bus)._process_message(
        {
            "type": "pmessage",
            "pattern": "chat.*",
            "data": json.dumps(
                {
                    "topic": "chat.tool.completed",
                    "payload": {"status": "ok"},
                }
            ),
        }
    )

    assert received == [{"status": "ok"}]


@pytest.mark.anyio
async def test_redis_event_bus_handler_exception_does_not_block_peers() -> None:
    """One failing handler should not prevent other handlers from running."""

    received: list[dict[str, object]] = []
    bus = RedisEventBus()

    async def failing_handler(payload: Mapping[str, object]) -> None:
        del payload
        raise RuntimeError("boom")

    async def successful_handler(payload: Mapping[str, object]) -> None:
        received.append(dict(payload))

    await bus.subscribe("chat.tool.completed", failing_handler)
    await bus.subscribe("chat.tool.completed", successful_handler)
    await cast(Any, bus)._process_message(
        {
            "type": "message",
            "data": json.dumps(
                {
                    "topic": "chat.tool.completed",
                    "payload": {"status": "ok"},
                }
            ),
        }
    )

    assert received == [{"status": "ok"}]
