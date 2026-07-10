"""Durable Redis Streams event bus."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from collections.abc import Mapping
from uuid import uuid4

import redis.asyncio as redis
from redis.exceptions import ResponseError

from app.contracts.ports.event_bus import EventHandler, IEventBus

logger = logging.getLogger(__name__)

_BLOCK_MILLISECONDS = 1_000
_STALE_MESSAGE_MILLISECONDS = 60_000


class RedisEventBus(IEventBus):
    """Publish and consume application events through Redis Streams."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._redis: redis.Redis | None = None
        self._running = False
        self._consumer_tasks: dict[str, asyncio.Task[None]] = {}
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.consumer_group = os.getenv("EVENT_CONSUMER_GROUP", "default")
        self.consumer_name = f"{socket.gethostname()}-{uuid4()}"

    async def publish(self, topic: str, payload: Mapping[str, object]) -> None:
        """Append an event to its durable topic stream."""
        if self._redis is None:
            raise RuntimeError(
                f"Redis EventBus not started (redis_url={self.redis_url})"
            )
        await self._redis.xadd(
            self._stream_name(topic),
            {
                "topic": topic,
                "payload": json.dumps(dict(payload), ensure_ascii=False),
            },
        )

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register an exact-topic handler in this consumer group."""
        if "*" in topic or "?" in topic:
            raise ValueError("Redis Streams subscriptions require an exact topic")
        self._handlers.setdefault(topic, []).append(handler)
        if self._running:
            await self._ensure_group(topic)
            self._start_consumer(topic)

    async def start(self) -> None:
        """Connect and start one consumer loop per subscribed topic."""
        if self._running:
            return
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
        self._running = True
        for topic in self._handlers:
            await self._ensure_group(topic)
            self._start_consumer(topic)

    async def stop(self) -> None:
        """Stop consumers and close the Redis connection."""
        self._running = False
        for task in self._consumer_tasks.values():
            task.cancel()
        if self._consumer_tasks:
            await asyncio.gather(
                *self._consumer_tasks.values(),
                return_exceptions=True,
            )
        self._consumer_tasks.clear()
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def _ensure_group(self, topic: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.xgroup_create(
                self._stream_name(topic),
                self.consumer_group,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _start_consumer(self, topic: str) -> None:
        if topic in self._consumer_tasks:
            return
        self._consumer_tasks[topic] = asyncio.create_task(self._consume(topic))

    async def _consume(self, topic: str) -> None:
        stream = self._stream_name(topic)
        while self._running and self._redis is not None:
            try:
                await self._claim_stale(topic)
                response = await self._redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {stream: ">"},
                    count=10,
                    block=_BLOCK_MILLISECONDS,
                )
                await self._process_stream_response(topic, response)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis stream consumer failed for %s", topic)
                await asyncio.sleep(1)

    async def _claim_stale(self, topic: str) -> None:
        if self._redis is None:
            return
        response = await self._redis.xautoclaim(
            self._stream_name(topic),
            self.consumer_group,
            self.consumer_name,
            min_idle_time=_STALE_MESSAGE_MILLISECONDS,
            start_id="0-0",
            count=10,
        )
        entries: object = response[1] if isinstance(response, (list, tuple)) else None
        if isinstance(entries, list):
            await self._process_entries(topic, entries)

    async def _process_stream_response(
        self,
        topic: str,
        response: object,
    ) -> None:
        if not isinstance(response, list):
            return
        for stream_entry in response:
            if not isinstance(stream_entry, (list, tuple)) or len(stream_entry) != 2:
                continue
            entries = stream_entry[1]
            if isinstance(entries, list):
                await self._process_entries(topic, entries)

    async def _process_entries(self, topic: str, entries: list[object]) -> None:
        if self._redis is None:
            return
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            message_id, fields = entry
            if not isinstance(message_id, str) or not isinstance(fields, dict):
                continue
            payload = self._decode_payload(fields.get("payload"))
            if payload is None:
                continue
            if await self._dispatch(topic, payload):
                await self._redis.xack(
                    self._stream_name(topic),
                    self.consumer_group,
                    message_id,
                )

    async def _dispatch(
        self,
        topic: str,
        payload: Mapping[str, object],
    ) -> bool:
        handlers = self._handlers.get(topic, [])
        if not handlers:
            return False
        results = await asyncio.gather(
            *(handler(payload) for handler in handlers),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, Exception)]
        for failure in failures:
            logger.error(
                "Event handler failed for topic %s: %s",
                topic,
                failure,
                exc_info=(type(failure), failure, failure.__traceback__),
            )
        return not failures

    @staticmethod
    def _decode_payload(raw_payload: object) -> dict[str, object] | None:
        if not isinstance(raw_payload, (str, bytes, bytearray)):
            return None
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.exception("Invalid Redis stream event payload")
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _stream_name(topic: str) -> str:
        return f"events:{topic}"
