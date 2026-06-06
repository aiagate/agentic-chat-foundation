"""Tests for tool call stores."""

from __future__ import annotations

from typing import Any

import pytest
from flow_res import is_err

import app.infrastructure.stores.retrieved_context_store as retrieved_store_module
import app.infrastructure.stores.tool_call_store as store_module
import app.infrastructure.stores.tool_execution_lock as lock_module
from app.contracts.messages.retrieved_context import RetrievedContext
from app.contracts.messages.tool_contracts import ToolCall
from app.infrastructure.stores.retrieved_context_store import (
    InMemoryRetrievedContextStore,
    RedisRetrievedContextStore,
)
from app.infrastructure.stores.tool_call_store import (
    InMemoryToolCallStore,
    RedisToolCallStore,
)
from app.infrastructure.stores.tool_execution_lock import (
    InMemoryToolExecutionLock,
    RedisToolExecutionLock,
)

CHARACTER_ID = "shirasagi-reina"


@pytest.mark.anyio
async def test_in_memory_tool_call_store_returns_copy() -> None:
    """Stored tool calls should be retrieved by ID without sharing mutable state."""

    store = InMemoryToolCallStore()
    tool_call = ToolCall(
        tool_call_id="tool-1",
        character_id=CHARACTER_ID,
        tool_name="web_search",
        arguments={"query": "hello"},
        user_message="searching",
    )

    save_result = await store.save(tool_call)
    loaded_result = await store.get("tool-1", character_id=CHARACTER_ID)

    assert not is_err(save_result)
    assert not is_err(loaded_result)
    loaded_result.value.arguments["query"] = "changed"
    reloaded_result = await store.get("tool-1", character_id=CHARACTER_ID)
    assert not is_err(reloaded_result)
    assert reloaded_result.value.arguments["query"] == "hello"


@pytest.mark.anyio
async def test_in_memory_tool_call_store_separates_characters() -> None:
    """The same tool_call_id can be owned by different characters."""

    store = InMemoryToolCallStore()
    await store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id="reina",
            tool_name="web_search",
            arguments={"query": "reina"},
            user_message="searching",
        )
    )
    await store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id="mio",
            tool_name="web_search",
            arguments={"query": "mio"},
            user_message="searching",
        )
    )

    reina = await store.get("tool-1", character_id="reina")
    mio = await store.get("tool-1", character_id="mio")

    assert not is_err(reina)
    assert not is_err(mio)
    assert reina.value.arguments == {"query": "reina"}
    assert mio.value.arguments == {"query": "mio"}


@pytest.mark.anyio
async def test_redis_tool_call_store_round_trips_payload(mocker: Any) -> None:
    """Redis store should save compact JSON by tool_call_id and restore ToolCall."""

    class RedisStub:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.ttl: int | None = None

        async def set(self, key: str, value: str, *, ex: int) -> None:
            self.values[key] = value
            self.ttl = ex

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

    redis_stub = RedisStub()
    mocker.patch.object(
        retrieved_store_module.redis,
        "from_url",
        return_value=redis_stub,
    )
    store = RedisToolCallStore(redis_url="redis://test", ttl_seconds=30)

    save_result = await store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
            tool_name="memory.search",
            arguments={"query": "memory"},
            user_message="checking memory",
        )
    )
    loaded_result = await store.get("tool-1", character_id=CHARACTER_ID)

    assert not is_err(save_result)
    assert redis_stub.ttl == 30
    assert not is_err(loaded_result)
    assert loaded_result.value.tool_name == "memory.search"
    assert loaded_result.value.arguments == {"query": "memory"}


@pytest.mark.anyio
async def test_redis_tool_call_store_uses_character_namespaced_keys(
    mocker: Any,
) -> None:
    """Redis tool calls should be isolated by character namespace."""

    class RedisStub:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def set(self, key: str, value: str, *, ex: int) -> None:
            del ex
            self.values[key] = value

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

    redis_stub = RedisStub()
    mocker.patch.object(store_module.redis, "from_url", return_value=redis_stub)
    store = RedisToolCallStore(redis_url="redis://test", ttl_seconds=30)

    await store.save(
        ToolCall(
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
            tool_name="web_search",
            arguments={"query": "reina"},
            user_message="searching",
        )
    )

    assert f"agent:{CHARACTER_ID}:tool_call:tool-1" in redis_stub.values
    assert is_err(await store.get("tool-1", character_id="mio"))
    loaded = await store.get("tool-1", character_id=CHARACTER_ID)
    assert not is_err(loaded)
    assert loaded.value.character_id == CHARACTER_ID


@pytest.mark.anyio
async def test_in_memory_retrieved_context_store_separates_characters() -> None:
    """Retrieved context should not cross character boundaries."""

    store = InMemoryRetrievedContextStore()
    await store.save(
        RetrievedContext(
            tool_call_id="tool-1",
            character_id="reina",
            query="query",
            tool_name="web_search",
            items=[],
            rendered_text="reina context",
        )
    )

    assert is_err(await store.get("tool-1", character_id="mio"))
    loaded = await store.get("tool-1", character_id="reina")
    assert not is_err(loaded)
    assert loaded.value.rendered_text == "reina context"


@pytest.mark.anyio
async def test_redis_retrieved_context_store_round_trips_payload(
    mocker: Any,
) -> None:
    """Redis retrieved context should round-trip with TTL and character keys."""

    class RedisStub:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.ttl: int | None = None

        async def set(self, key: str, value: str, *, ex: int) -> None:
            self.values[key] = value
            self.ttl = ex

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

    redis_stub = RedisStub()
    mocker.patch.object(
        lock_module.redis,
        "from_url",
        return_value=redis_stub,
    )
    store = RedisRetrievedContextStore(redis_url="redis://test", ttl_seconds=45)

    save_result = await store.save(
        RetrievedContext(
            tool_call_id="tool-1",
            character_id="reina",
            query="current info",
            tool_name="web_search",
            items=[],
            rendered_text="## Retrieved Context",
        )
    )
    loaded_result = await store.get("tool-1", character_id="reina")

    assert not is_err(save_result)
    assert redis_stub.ttl == 45
    assert "agent:reina:retrieved_context:tool-1" in redis_stub.values
    assert not is_err(loaded_result)
    assert loaded_result.value.character_id == "reina"
    assert loaded_result.value.rendered_text == "## Retrieved Context"


@pytest.mark.anyio
async def test_in_memory_tool_execution_lock_separates_characters() -> None:
    """Execution locks should only block duplicates for the same character."""

    lock = InMemoryToolExecutionLock()

    first_reina = await lock.acquire("tool-1", character_id="reina")
    second_reina = await lock.acquire("tool-1", character_id="reina")
    first_mio = await lock.acquire("tool-1", character_id="mio")

    assert not is_err(first_reina)
    assert not is_err(second_reina)
    assert not is_err(first_mio)
    assert first_reina.value is True
    assert second_reina.value is False
    assert first_mio.value is True


@pytest.mark.anyio
async def test_redis_tool_execution_lock_uses_set_nx(
    mocker: Any,
) -> None:
    """Redis execution locks should use SET NX with a TTL."""

    class RedisStub:
        def __init__(self) -> None:
            self.values: set[str] = set()
            self.calls: list[tuple[str, str, int, bool]] = []

        async def set(
            self,
            key: str,
            value: str,
            *,
            ex: int,
            nx: bool,
        ) -> bool:
            self.calls.append((key, value, ex, nx))
            if nx and key in self.values:
                return False
            self.values.add(key)
            return True

    redis_stub = RedisStub()
    mocker.patch.object(
        store_module.redis,
        "from_url",
        return_value=redis_stub,
    )
    lock = RedisToolExecutionLock(redis_url="redis://test", ttl_seconds=45)

    first = await lock.acquire("tool-1", character_id="reina")
    second = await lock.acquire("tool-1", character_id="reina")

    assert not is_err(first)
    assert not is_err(second)
    assert first.value is True
    assert second.value is False
    assert redis_stub.calls == [
        ("agent:reina:tool_execution:tool-1", "1", 45, True),
        ("agent:reina:tool_execution:tool-1", "1", 45, True),
    ]
