"""Tests for dependency injection bindings."""

from pathlib import Path

import pytest
from injector import Injector

from app import container
from app.application.agent import (
    AgentReplyPersistence,
    AgentRunCoordinator,
    AgentToolCoordinator,
)
from app.contracts.ports.agent_inference_context import IAgentInferenceContextService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.messaging.in_memory_event_bus import InMemoryEventBus
from app.infrastructure.messaging.redis_event_bus import RedisEventBus
from app.infrastructure.services.agent_inference_context import (
    AgentInferenceContextService,
)
from app.infrastructure.services.memory_consolidation import MemoryConsolidationService
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from tests._agent_profile_fixture import copy_agent_profile_bundle


@pytest.mark.anyio
async def test_di_container_binds_durable_agent_components(
    test_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("MEMORY_ROOT", str(memory_root))
    copy_agent_profile_bundle(memory_root)
    injector = Injector([container.configure])

    assert isinstance(injector.get(IUnitOfWork), SQLAlchemyUnitOfWork)
    assert isinstance(injector.get(IMemoryStore), FilesystemMemoryStore)
    assert isinstance(injector.get(IMemoryService), FilesystemMemoryService)
    assert isinstance(
        injector.get(IMemoryConsolidationService), MemoryConsolidationService
    )
    assert isinstance(
        injector.get(IAgentInferenceContextService), AgentInferenceContextService
    )
    assert isinstance(injector.get(AgentReplyPersistence), AgentReplyPersistence)
    assert isinstance(injector.get(AgentRunCoordinator), AgentRunCoordinator)
    assert isinstance(injector.get(AgentToolCoordinator), AgentToolCoordinator)


@pytest.mark.anyio
async def test_event_bus_defaults_to_memory(test_db_engine: None) -> None:
    import os

    os.environ.pop("EVENT_BUS_PROVIDER", None)
    os.environ.pop("REDIS_URL", None)
    injector = Injector([container.configure])
    assert isinstance(injector.get(IEventBus), InMemoryEventBus)


@pytest.mark.anyio
async def test_event_bus_selects_redis(
    test_db_engine: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVENT_BUS_PROVIDER", "redis")
    injector = Injector([container.configure])
    assert isinstance(injector.get(IEventBus), RedisEventBus)
