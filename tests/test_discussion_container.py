"""Dependency-injection test for autonomous Discord discussions."""

from pathlib import Path

import pytest
from injector import Injector

from app import container
from app.application.discussion import (
    LocalAutonomousTopicGuard,
    LocalSpeechGuard,
    StructuredAgentTurnEvaluator,
    StructuredAutonomousTopicEvaluator,
)
from app.contracts.ports.discussion import (
    IAgentTurnEvaluator,
    IAutonomousTopicEvaluator,
    IAutonomousTopicGuard,
    IAutonomousTopicRepository,
    IDiscussionRepository,
    ILocalSpeechGuard,
)
from app.infrastructure.repositories.discussion_repository import (
    SQLAlchemyDiscussionRepository,
)
from app.usecases.discussion.generate_autonomous_topic import (
    GenerateAutonomousTopicHandler,
)
from app.usecases.discussion.process_discussion_message import (
    ProcessDiscussionMessageHandler,
)
from tests._agent_profile_fixture import copy_agent_profile_bundle


@pytest.mark.anyio
async def test_di_container_binds_discussion_components(
    test_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    memory_root = tmp_path / "memory"
    monkeypatch.setenv("MEMORY_ROOT", str(memory_root))
    copy_agent_profile_bundle(memory_root)
    injector = Injector([container.configure])

    assert isinstance(
        injector.get(IDiscussionRepository), SQLAlchemyDiscussionRepository
    )
    assert isinstance(injector.get(IAgentTurnEvaluator), StructuredAgentTurnEvaluator)
    assert isinstance(injector.get(ILocalSpeechGuard), LocalSpeechGuard)
    assert isinstance(
        injector.get(IAutonomousTopicRepository), SQLAlchemyDiscussionRepository
    )
    assert isinstance(
        injector.get(IAutonomousTopicEvaluator),
        StructuredAutonomousTopicEvaluator,
    )
    assert isinstance(injector.get(IAutonomousTopicGuard), LocalAutonomousTopicGuard)
    assert isinstance(
        injector.get(ProcessDiscussionMessageHandler),
        ProcessDiscussionMessageHandler,
    )
    assert isinstance(
        injector.get(GenerateAutonomousTopicHandler),
        GenerateAutonomousTopicHandler,
    )
