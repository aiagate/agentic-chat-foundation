"""Tests for the durable Redis Streams event bus."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

import pytest

from app.infrastructure.messaging.redis_event_bus import RedisEventBus


class _RedisStreamsStub:
    def __init__(self) -> None:
        self.added: list[tuple[str, dict[str, str]]] = []
        self.acked: list[tuple[str, str, str]] = []

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        self.added.append((stream, fields))
        return "1-0"

    async def xack(self, stream: str, group: str, message_id: str) -> int:
        self.acked.append((stream, group, message_id))
        return 1


@pytest.mark.anyio
async def test_redis_event_bus_publish_requires_start() -> None:
    bus = RedisEventBus()

    with pytest.raises(RuntimeError):
        await bus.publish("agent.tool.requested", {"tool_call_id": "tool-1"})


@pytest.mark.anyio
async def test_redis_event_bus_publish_appends_to_topic_stream() -> None:
    bus = RedisEventBus()
    redis_stub = _RedisStreamsStub()
    cast(Any, bus)._redis = redis_stub

    await bus.publish("agent.tool.requested", {"tool_call_id": "tool-1"})

    assert redis_stub.added == [
        (
            "events:agent.tool.requested",
            {
                "topic": "agent.tool.requested",
                "payload": json.dumps(
                    {"tool_call_id": "tool-1"},
                    ensure_ascii=False,
                ),
            },
        )
    ]


@pytest.mark.anyio
async def test_redis_event_bus_acks_after_handler_success() -> None:
    received: list[dict[str, object]] = []
    bus = RedisEventBus()
    redis_stub = _RedisStreamsStub()
    cast(Any, bus)._redis = redis_stub

    async def handler(payload: Mapping[str, object]) -> None:
        received.append(dict(payload))

    await bus.subscribe("agent.tool.requested", handler)
    await cast(Any, bus)._process_entries(
        "agent.tool.requested",
        [("1-0", {"payload": json.dumps({"tool_call_id": "tool-1"})})],
    )

    assert received == [{"tool_call_id": "tool-1"}]
    assert redis_stub.acked == [
        ("events:agent.tool.requested", bus.consumer_group, "1-0")
    ]


@pytest.mark.anyio
async def test_redis_event_bus_does_not_ack_handler_failure() -> None:
    bus = RedisEventBus()
    redis_stub = _RedisStreamsStub()
    cast(Any, bus)._redis = redis_stub

    async def failing_handler(payload: Mapping[str, object]) -> None:
        del payload
        raise RuntimeError("boom")

    await bus.subscribe("agent.run.wakeup", failing_handler)
    await cast(Any, bus)._process_entries(
        "agent.run.wakeup",
        [("1-0", {"payload": json.dumps({"status": "ok"})})],
    )

    assert redis_stub.acked == []


@pytest.mark.anyio
async def test_redis_event_bus_rejects_pattern_subscriptions() -> None:
    bus = RedisEventBus()

    async def handler(payload: Mapping[str, object]) -> None:
        del payload

    with pytest.raises(ValueError, match="exact topic"):
        await bus.subscribe("chat.*", handler)
