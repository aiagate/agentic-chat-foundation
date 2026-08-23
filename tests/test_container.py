"""Tests for dependency injection bindings."""

from pathlib import Path

import pytest
from injector import Injector

from app import container
from app.contracts.ports.agent_inference_context import IAgentInferenceContextService
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_service import IMemoryService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.unit_of_work import IUnitOfWorkFactory
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.services.agent_inference_context import (
    AgentInferenceContextService,
)
from app.infrastructure.services.memory_consolidation import MemoryConsolidationService
from app.infrastructure.services.memory_service import FilesystemMemoryService
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWorkFactory
from tests._agent_profile_fixture import copy_agent_profile_bundle


@pytest.mark.anyio
async def test_di_container_binds_conversation_components(
    test_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("MEMORY_ROOT", str(memory_root))
    copy_agent_profile_bundle(memory_root)
    injector = Injector([container.configure])

    assert isinstance(injector.get(IUnitOfWorkFactory), SQLAlchemyUnitOfWorkFactory)
    assert isinstance(injector.get(IMemoryStore), FilesystemMemoryStore)
    assert isinstance(injector.get(IMemoryService), FilesystemMemoryService)
    assert isinstance(
        injector.get(IMemoryConsolidationService), MemoryConsolidationService
    )
    assert isinstance(
        injector.get(IAgentInferenceContextService), AgentInferenceContextService
    )
