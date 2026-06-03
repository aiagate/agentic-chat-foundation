"""In-memory tool call store."""

from __future__ import annotations

import logging
import os

import redis.asyncio as redis
from flow_res import Err, Ok, Result
from pydantic import ValidationError

from app.contracts.messages.character_definition import selected_character_id
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.tool_call_store import IToolCallStore, ToolCallStoreError

logger = logging.getLogger(__name__)


class InMemoryToolCallStore(IToolCallStore):
    """Keep tool calls in memory for the current process."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], ToolCall] = {}

    async def save(self, tool_call: ToolCall) -> Result[None, ToolCallStoreError]:
        tool_call_id = tool_call.tool_call_id
        if not tool_call_id:
            return Err(ToolCallStoreError("Tool call ID is required"))

        character_id = _character_id(tool_call.character_id)
        self._store[(character_id, tool_call_id)] = tool_call.model_copy(deep=True)
        logger.debug(
            "Saved tool call: tool_call_id=%s tool_name=%s",
            tool_call_id,
            tool_call.tool_name,
        )
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[ToolCall, ToolCallStoreError]:
        tool_call = self._store.get((_character_id(character_id), tool_call_id))
        if tool_call is None:
            logger.debug("Tool call miss: tool_call_id=%s", tool_call_id)
            return Err(ToolCallStoreError(f"Tool call not found: {tool_call_id}"))

        logger.debug(
            "Loaded tool call: tool_call_id=%s tool_name=%s",
            tool_call_id,
            tool_call.tool_name,
        )
        return Ok(tool_call.model_copy(deep=True))


class RedisToolCallStore(IToolCallStore):
    """Store short-lived tool calls in Redis for cross-process workers."""

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._ttl_seconds = ttl_seconds or int(os.getenv("TOOL_CALL_STORE_TTL", "900"))
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def save(self, tool_call: ToolCall) -> Result[None, ToolCallStoreError]:
        tool_call_id = tool_call.tool_call_id
        if not tool_call_id:
            return Err(ToolCallStoreError("Tool call ID is required"))

        try:
            await self._redis.set(
                _key(tool_call_id, character_id=_character_id(tool_call.character_id)),
                tool_call.model_dump_json(exclude_none=True),
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            logger.exception("Failed to save tool call: tool_call_id=%s", tool_call_id)
            return Err(ToolCallStoreError(str(exc)))

        logger.debug(
            "Saved Redis tool call: tool_call_id=%s tool_name=%s",
            tool_call_id,
            tool_call.tool_name,
        )
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[ToolCall, ToolCallStoreError]:
        try:
            payload = await self._redis.get(
                _key(tool_call_id, character_id=_character_id(character_id))
            )
        except Exception as exc:
            logger.exception("Failed to load tool call: tool_call_id=%s", tool_call_id)
            return Err(ToolCallStoreError(str(exc)))

        if payload is None:
            logger.debug("Redis tool call miss: tool_call_id=%s", tool_call_id)
            return Err(ToolCallStoreError(f"Tool call not found: {tool_call_id}"))

        try:
            tool_call = ToolCall.model_validate_json(payload)
        except ValidationError as exc:
            logger.warning(
                "Invalid stored tool call payload: tool_call_id=%s",
                tool_call_id,
            )
            return Err(ToolCallStoreError(str(exc)))

        logger.debug(
            "Loaded Redis tool call: tool_call_id=%s tool_name=%s",
            tool_call_id,
            tool_call.tool_name,
        )
        return Ok(tool_call)


def _character_id(value: str | None) -> str:
    return value or selected_character_id()


def _key(tool_call_id: str, *, character_id: str) -> str:
    return f"agent:{character_id}:tool_call:{tool_call_id}"
