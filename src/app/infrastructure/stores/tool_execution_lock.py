"""Tool execution idempotency lock implementations."""

from __future__ import annotations

import logging
import os

import redis.asyncio as redis
from flow_res import Err, Ok, Result

from app.contracts.ports.tool_execution_lock import (
    IToolExecutionLock,
    ToolExecutionLockError,
)

logger = logging.getLogger(__name__)


class InMemoryToolExecutionLock(IToolExecutionLock):
    """Keep execution locks in memory for the current process."""

    def __init__(self) -> None:
        self._locked: set[tuple[str, str]] = set()

    async def acquire(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[bool, ToolExecutionLockError]:
        key = (character_id, tool_call_id)
        if key in self._locked:
            return Ok(False)
        self._locked.add(key)
        return Ok(True)


class RedisToolExecutionLock(IToolExecutionLock):
    """Use Redis SET NX as a cross-process execution lock."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._ttl_seconds = ttl_seconds or int(
            os.getenv("TOOL_EXECUTION_LOCK_TTL", "900")
        )
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def acquire(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[bool, ToolExecutionLockError]:
        try:
            acquired = await self._redis.set(
                _key(tool_call_id, character_id=character_id),
                "1",
                ex=self._ttl_seconds,
                nx=True,
            )
        except Exception as exc:
            logger.exception(
                "Failed to acquire tool execution lock: tool_call_id=%s",
                tool_call_id,
            )
            return Err(ToolExecutionLockError(str(exc)))
        return Ok(bool(acquired))


def _key(tool_call_id: str, *, character_id: str) -> str:
    return f"agent:{character_id}:tool_execution:{tool_call_id}"
