"""In-memory retrieved context store."""

from __future__ import annotations

import logging
import os

import redis.asyncio as redis
from flow_res import Err, Ok, Result
from pydantic import ValidationError

from app.contracts.messages.character_definition import selected_character_id
from app.contracts.messages.retrieved_context import RetrievedContext
from app.contracts.ports.retrieved_context_store import (
    IRetrievedContextStore,
    RetrievedContextStoreError,
)

logger = logging.getLogger(__name__)


class InMemoryRetrievedContextStore(IRetrievedContextStore):
    """Keep retrieved context in memory for the current process."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], RetrievedContext] = {}

    async def save(
        self,
        context: RetrievedContext,
    ) -> Result[None, RetrievedContextStoreError]:
        character_id = _character_id(context.character_id)
        self._store[(character_id, context.tool_call_id)] = context.model_copy(
            deep=True
        )
        logger.debug(
            "Saved retrieved context: tool_call_id=%s tool_name=%s items=%d",
            context.tool_call_id,
            context.tool_name,
            len(context.items),
        )
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[RetrievedContext, RetrievedContextStoreError]:
        context = self._store.get((_character_id(character_id), tool_call_id))
        if context is None:
            logger.debug("Retrieved context miss: tool_call_id=%s", tool_call_id)
            return Err(
                RetrievedContextStoreError(
                    f"Retrieved context not found: {tool_call_id}",
                )
            )
        logger.debug(
            "Loaded retrieved context: tool_call_id=%s tool_name=%s items=%d",
            tool_call_id,
            context.tool_name,
            len(context.items),
        )
        return Ok(context.model_copy(deep=True))


class RedisRetrievedContextStore(IRetrievedContextStore):
    """Store short-lived retrieved context in Redis for cross-process re-entry."""

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
            os.getenv("RETRIEVED_CONTEXT_STORE_TTL", "900")
        )
        self._redis = redis.from_url(self._redis_url, decode_responses=True)

    async def save(
        self,
        context: RetrievedContext,
    ) -> Result[None, RetrievedContextStoreError]:
        try:
            await self._redis.set(
                _key(
                    context.tool_call_id,
                    character_id=_character_id(context.character_id),
                ),
                context.model_dump_json(exclude_none=True),
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            logger.exception(
                "Failed to save retrieved context: tool_call_id=%s",
                context.tool_call_id,
            )
            return Err(RetrievedContextStoreError(str(exc)))
        return Ok(None)

    async def get(
        self,
        tool_call_id: str,
        *,
        character_id: str | None = None,
    ) -> Result[RetrievedContext, RetrievedContextStoreError]:
        try:
            payload = await self._redis.get(
                _key(tool_call_id, character_id=_character_id(character_id))
            )
        except Exception as exc:
            logger.exception(
                "Failed to load retrieved context: tool_call_id=%s",
                tool_call_id,
            )
            return Err(RetrievedContextStoreError(str(exc)))

        if payload is None:
            return Err(
                RetrievedContextStoreError(
                    f"Retrieved context not found: {tool_call_id}"
                )
            )

        try:
            return Ok(RetrievedContext.model_validate_json(payload))
        except ValidationError as exc:
            return Err(RetrievedContextStoreError(str(exc)))


def _character_id(value: str | None) -> str:
    return value or selected_character_id()


def _key(tool_call_id: str, *, character_id: str) -> str:
    return f"agent:{character_id}:retrieved_context:{tool_call_id}"
