"""Short-lived tool result store implementations."""

from __future__ import annotations

import os

import redis.asyncio as redis
from flow_res import Err, Ok, Result
from pydantic import ValidationError

from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.tool_result_store import (
    IToolResultStore,
    ToolResultStoreError,
)


class InMemoryToolResultStore(IToolResultStore):
    """Keep tool results in memory for the current process."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], ToolResultContext] = {}

    async def save(
        self,
        context: ToolResultContext,
    ) -> Result[None, ToolResultStoreError]:
        self._store[(context.character_id, context.tool_call_id)] = context.model_copy(
            deep=True
        )
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[ToolResultContext, ToolResultStoreError]:
        context = self._store.get((character_id, tool_call_id))
        if context is None:
            return Err(ToolResultStoreError(f"Tool result not found: {tool_call_id}"))
        return Ok(context.model_copy(deep=True))


class RedisToolResultStore(IToolResultStore):
    """Store tool results in Redis for cross-process agent re-entry."""

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
            os.getenv("TOOL_RESULT_STORE_TTL", "900")
        )
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def save(
        self,
        context: ToolResultContext,
    ) -> Result[None, ToolResultStoreError]:
        try:
            await self._redis.set(
                _key(context.tool_call_id, character_id=context.character_id),
                context.model_dump_json(exclude_none=True),
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            return Err(ToolResultStoreError(str(exc)))
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str,
    ) -> Result[ToolResultContext, ToolResultStoreError]:
        try:
            payload = await self._redis.get(
                _key(tool_call_id, character_id=character_id)
            )
        except Exception as exc:
            return Err(ToolResultStoreError(str(exc)))
        if payload is None:
            return Err(ToolResultStoreError(f"Tool result not found: {tool_call_id}"))
        try:
            return Ok(ToolResultContext.model_validate_json(payload))
        except ValidationError as exc:
            return Err(ToolResultStoreError(str(exc)))


def _key(tool_call_id: str, *, character_id: str) -> str:
    return f"agent:{character_id}:tool_result:{tool_call_id}"
