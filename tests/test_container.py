"""Tests for the dependency injection container."""

import pytest
from injector import Injector

from app import container
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.tool_execution_lock import IToolExecutionLock
from app.domain.repositories import IUnitOfWork
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from app.infrastructure.messaging.redis_event_bus import RedisEventBus
from app.infrastructure.services.memory_consolidation import (
    MemoryConsolidationService,
)
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.stores.tool_execution_lock import RedisToolExecutionLock
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork


@pytest.mark.anyio
async def test_di_container_bindings(test_db_engine: None) -> None:
    """Test that the DI container is configured correctly."""
    injector = Injector([container.configure])

    # Test that requesting the IUnitOfWork interface returns the correct implementation
    uow_instance = injector.get(IUnitOfWork)
    memory_store = injector.get(IMemoryStore)
    memory_consolidation_service = injector.get(IMemoryConsolidationService)
    memory_service = injector.get(IMemoryService)

    assert isinstance(uow_instance, SQLAlchemyUnitOfWork)
    assert isinstance(memory_store, FilesystemMemoryStore)
    assert isinstance(
        memory_consolidation_service,
        MemoryConsolidationService,
    )
    assert isinstance(memory_service, FilesystemMemoryService)


@pytest.mark.anyio
async def test_di_container_event_bus_defaults_to_memory(test_db_engine: None) -> None:
    """Test that the container defaults to the in-memory event bus."""
    import os

    os.environ.pop("EVENT_BUS_PROVIDER", None)
    os.environ.pop("REDIS_URL", None)
    injector = Injector([container.configure])
    event_bus = injector.get(IEventBus)

    assert isinstance(event_bus, InMemoryEventBus)


@pytest.mark.anyio
async def test_di_container_event_bus_selects_redis(
    test_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the container selects Redis when configured."""
    monkeypatch.setenv("EVENT_BUS_PROVIDER", "redis")
    injector = Injector([container.configure])
    event_bus = injector.get(IEventBus)

    assert isinstance(event_bus, RedisEventBus)


@pytest.mark.anyio
async def test_di_container_selects_redis_tool_execution_lock(
    test_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Redis-backed runs use a cross-process execution lock."""

    monkeypatch.setenv("REDIS_URL", "redis://test")
    injector = Injector([container.configure])
    lock = injector.get(IToolExecutionLock)

    assert isinstance(lock, RedisToolExecutionLock)
