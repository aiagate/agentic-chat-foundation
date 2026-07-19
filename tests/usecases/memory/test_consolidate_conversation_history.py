"""Tests for the long-term memory organization use case."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import Ok, Result, is_err
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import CharacterDefinition
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_consolidation import MemoryConsolidationResult
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.unit_of_work import IUnitOfWork, IUnitOfWorkFactory
from app.domain.queries.raw_chat_log_query import LongTermMemorySourceItem
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.orm_models import (
    ChatORM,
    UserChannelIdentityORM,
    UserORM,
)
from app.infrastructure.queries.long_term_memory_query_service import (
    LongTermMemoryQueryService,
    LongTermMemoryTarget,
)
from app.infrastructure.services.memory_consolidation import MemoryConsolidationService
from app.infrastructure.services.memory_semantic_extraction import (
    MemorySemanticExtractionService,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWorkFactory
from app.usecases.memory.consolidate_conversation_history import (
    ConsolidateConversationHistoryCommand,
    ConsolidateConversationHistoryHandler,
)
from tests._relationship_fixture import relationship_definition


class _FakeAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AGENT_PROFILE_BUNDLE


AGENT_PROFILE_BUNDLE = AgentProfileBundle(
    character=CharacterDefinition(character_id="shirasagi-reina"),
    persona_context="Persona Contract:\n- test persona",
    relationship=relationship_definition(),
)


def _configure_relationship_repository(uow: Any, mocker: Any) -> Any:
    repository = mocker.Mock()
    repository.reconcile_confirmed = AsyncMock(return_value=Ok(None))
    uow.GetCharacterRelationshipRepository = mocker.Mock(return_value=repository)
    return repository


@pytest.mark.anyio
async def test_consolidate_conversation_history_invokes_consolidation_service(
    mocker: Any,
) -> None:
    """The organization command delegates to the consolidation port."""

    uow = mocker.Mock(spec=IUnitOfWork)
    uow_factory = mocker.Mock(spec=IUnitOfWorkFactory)
    uow_factory.create = mocker.Mock(return_value=uow)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    source_repository = mocker.Mock()
    source_repository.mark_consolidated = AsyncMock(return_value=Ok(2))
    uow.GetMemoryConsolidatedChatSourceRepository = mocker.Mock(
        return_value=source_repository
    )
    _configure_relationship_repository(uow, mocker)
    uow.commit = AsyncMock(return_value=Ok(None))
    long_term_memory_query = mocker.Mock(spec=LongTermMemoryQueryService)
    long_term_memory_query.list_pending_targets = AsyncMock(
        return_value=[
            LongTermMemoryTarget(
                character_id="shirasagi-reina",
                user_id="u1",
                day=datetime(2026, 5, 18).date(),
                raw_logs=[
                    _long_term_memory_source_item(
                        "raw-1",
                        chat_type=ChatType.DISCORD,
                        created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    ),
                    _long_term_memory_source_item(
                        "raw-2",
                        chat_type=ChatType.LINE,
                        created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    ),
                ],
            )
        ]
    )
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.consolidate_chat_logs = AsyncMock(
        return_value=MemoryConsolidationResult(
            evaluated_chat_ids=("raw-1", "raw-2"),
            deferred_chat_ids=(),
            episode_upserted_count=2,
        )
    )

    handler = ConsolidateConversationHistoryHandler(
        uow_factory,
        consolidation_service,
        long_term_memory_query,
        _FakeAgentProfileService(),
        "shirasagi-reina",
    )

    result = await handler.handle(
        ConsolidateConversationHistoryCommand(
            reference_time=datetime(2026, 5, 19, tzinfo=UTC)
        )
    )

    assert not is_err(result)
    assert result.value.evaluated_chat_count == 2
    assert result.value.episode_upserted_count == 2
    assert uow.GetRawChatLogQuery.call_count == 1
    long_term_memory_query.list_pending_targets.assert_awaited_once_with(
        raw_chat_log_query,
        character_id="shirasagi-reina",
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )
    consolidation_stub = cast(Any, consolidation_service.consolidate_chat_logs)
    consolidation_stub.assert_awaited_once()
    await_args = consolidation_stub.await_args
    assert await_args is not None
    assert await_args.args == ()
    assert await_args.kwargs["user_id"] == "u1"
    assert await_args.kwargs["day"] == datetime(2026, 5, 18).date()
    assert [raw_log.id for raw_log in await_args.kwargs["raw_logs"]] == [
        "raw-1",
        "raw-2",
    ]
    assert await_args.kwargs["reference_time"] == datetime(2026, 5, 19, tzinfo=UTC)
    source_repository.mark_consolidated.assert_awaited_once_with(
        ["raw-1", "raw-2"],
        consolidated_at=datetime(2026, 5, 19, tzinfo=UTC),
    )
    uow.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_consolidate_conversation_history_reports_failures(
    mocker: Any,
) -> None:
    """Test that consolidation failures are surfaced as use case errors."""

    uow = mocker.Mock(spec=IUnitOfWork)
    uow_factory = mocker.Mock(spec=IUnitOfWorkFactory)
    uow_factory.create = mocker.Mock(return_value=uow)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    long_term_memory_query = mocker.Mock(spec=LongTermMemoryQueryService)
    long_term_memory_query.list_pending_targets = AsyncMock(
        return_value=[
            LongTermMemoryTarget(
                character_id="shirasagi-reina",
                user_id="u1",
                day=datetime(2026, 5, 18).date(),
                raw_logs=[
                    _long_term_memory_source_item(
                        "raw-1",
                        chat_type=ChatType.DISCORD,
                        created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    )
                ],
            )
        ]
    )
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.consolidate_chat_logs = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    handler = ConsolidateConversationHistoryHandler(
        uow_factory,
        consolidation_service,
        long_term_memory_query,
        _FakeAgentProfileService(),
        "shirasagi-reina",
    )

    result = await handler.handle(ConsolidateConversationHistoryCommand())

    assert is_err(result)
    assert uow.GetRawChatLogQuery.call_count == 1


@pytest.mark.anyio
async def test_consolidate_conversation_history_does_not_use_run_repository(
    mocker: Any,
) -> None:
    """Test that the handler no longer depends on a run repository."""

    uow = mocker.Mock(spec=IUnitOfWork)
    uow_factory = mocker.Mock(spec=IUnitOfWorkFactory)
    uow_factory.create = mocker.Mock(return_value=uow)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    long_term_memory_query = mocker.Mock(spec=LongTermMemoryQueryService)
    long_term_memory_query.list_pending_targets = AsyncMock(return_value=[])
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.consolidate_chat_logs = AsyncMock(
        return_value=MemoryConsolidationResult((), ())
    )

    handler = ConsolidateConversationHistoryHandler(
        uow_factory,
        consolidation_service,
        long_term_memory_query,
        _FakeAgentProfileService(),
        "shirasagi-reina",
    )

    result = await handler.handle(ConsolidateConversationHistoryCommand())

    assert not is_err(result)
    assert result.value.evaluated_chat_count == 0
    consolidation_service.consolidate_chat_logs.assert_not_awaited()


@pytest.mark.anyio
async def test_consolidate_conversation_history_consolidates_sqlite_raw_logs(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """End-to-end organization should read raw logs and write memory documents."""

    await _seed_raw_chat_logs(session_factory)

    memory_store = FilesystemMemoryStore(tmp_path / "memory")
    uow_factory = SQLAlchemyUnitOfWorkFactory(session_factory)
    long_term_memory_query = LongTermMemoryQueryService()
    handler = ConsolidateConversationHistoryHandler(
        uow_factory,
        MemoryConsolidationService(
            store=memory_store,
            semantic_extraction_service=MemorySemanticExtractionService(
                _FakeAIService(),
                _FakeAgentProfileService(),
            ),
            agent_profile_service=_FakeAgentProfileService(),
        ),
        long_term_memory_query,
        _FakeAgentProfileService(),
        "shirasagi-reina",
    )

    result = await handler.handle(
        ConsolidateConversationHistoryCommand(
            reference_time=datetime(2026, 5, 19, tzinfo=UTC)
        )
    )

    assert not is_err(result)
    assert result.value.evaluated_chat_count == 2
    assert result.value.episode_upserted_count == 2

    episode_documents = [
        memory_store.read_document(
            path,
            expected_memory_type="timeline",
            expected_user_id="u1",
        )
        for path in memory_store.iter_timeline_paths("u1")
    ]
    episodes_by_source = {
        tuple(cast(list[str], document.front_matter["source_chat_ids"])): document
        for document in episode_documents
    }
    morning = episodes_by_source[("raw-yesterday-discord",)]
    work = episodes_by_source[("raw-yesterday-line",)]
    assert morning.front_matter["timeline_type"] == "section_summary"
    assert str(morning.front_matter["memory_id"]).startswith(
        "timeline:episode-2026-05-18-"
    )
    assert morning.front_matter["manifest_title"] == "Morning routine"
    assert (
        morning.front_matter["manifest_summary"]
        == "Started the day early | The early start was noted."
    )
    assert len(str(morning.front_matter["section_slug"])) == 16
    assert morning.front_matter["summary_of"] == ["raw-yesterday-discord"]
    assert morning.front_matter["source_chat_ids"] == ["raw-yesterday-discord"]
    assert "Started the day early" in morning.body
    assert "Felt a little sleepy." in morning.body
    assert "Source Chat IDs" not in morning.body
    assert "Evidence" not in morning.body
    assert len(str(work.front_matter["section_slug"])) == 16
    assert work.front_matter["summary_of"] == ["raw-yesterday-line"]
    assert work.front_matter["source_chat_ids"] == ["raw-yesterday-line"]
    assert str(work.front_matter["memory_id"]).startswith(
        "timeline:episode-2026-05-18-"
    )
    assert work.front_matter["manifest_title"] == "Work progress"
    assert (
        work.front_matter["manifest_summary"]
        == "Reviewed implementation | Compatibility removal was reviewed."
    )
    assert "Reviewed implementation" in work.body
    assert "Compatibility removal was reviewed." in work.body
    assert "Source Chat IDs" not in work.body
    assert "Evidence" not in work.body

    async with session_factory() as session:
        result = await session.execute(select(ChatORM))
        rows = result.scalars().all()

    assert len(rows) == 3
    assert sorted(row.id for row in rows if row.id is not None) == [
        "raw-today-discord",
        "raw-yesterday-discord",
        "raw-yesterday-line",
    ]


async def _seed_raw_chat_logs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Insert deterministic raw chat logs for organization tests."""

    async with session_factory() as session:
        session.add_all(
            [
                UserORM(id="u1"),
                UserChannelIdentityORM(
                    user_id="u1",
                    channel="discord",
                    external_participant_id="u1",
                ),
                UserChannelIdentityORM(
                    user_id="u1",
                    channel="line",
                    external_participant_id="u1",
                ),
                ChatORM(
                    id="raw-yesterday-discord",
                    channel="discord",
                    external_conversation_id="channel-1",
                    external_participant_id="discord-user-1",
                    user_id="u1",
                    accepted_sequence=1,
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {
                            "texts": ["Yesterday should be consolidated."],
                        },
                    },
                    created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    channel_metadata={"guild_id": "guild-1", "channel_id": "channel-1"},
                ),
                ChatORM(
                    id="raw-yesterday-line",
                    channel="line",
                    external_conversation_id="line-user-1",
                    external_participant_id="line-user-1",
                    user_id="u1",
                    accepted_sequence=2,
                    role="assistant",
                    message_content={
                        "type": "TEXT",
                        "payload": {
                            "texts": ["Daily summary should include raw SQL logs."],
                        },
                    },
                    created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    channel_metadata={},
                ),
                ChatORM(
                    id="raw-today-discord",
                    channel="discord",
                    external_conversation_id="channel-1",
                    external_participant_id="discord-user-1",
                    user_id="u1",
                    accepted_sequence=3,
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"texts": ["Today should remain pending."]},
                    },
                    created_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
                    channel_metadata={"guild_id": "guild-1", "channel_id": "channel-1"},
                ),
            ]
        )
        await session.commit()


def _long_term_memory_source_item(
    raw_id: str,
    *,
    chat_type: ChatType,
    created_at: datetime,
) -> LongTermMemorySourceItem:
    return LongTermMemorySourceItem(
        id=raw_id,
        character_id="shirasagi-reina",
        user_id="u1",
        role="user",
        chat_type=chat_type,
        message_content={"type": "TEXT", "payload": {"texts": [raw_id]}},
        created_at=created_at,
    )


class _FakeAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
        tool_results: list[ToolResultContext] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions, tool_results
        payload = {
            "sections": [
                {
                    "id": "u1-2026-05-18-morning-routine",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "morning-routine",
                    "title": "Morning routine",
                    "source_chat_ids": ["raw-yesterday-discord"],
                    "summary": {
                        "topic": "Started the day early",
                        "self_feeling": "Felt a little sleepy.",
                        "other_feeling": "Supportive.",
                        "outcome": "The early start was noted.",
                    },
                    "entity_ids": [],
                    "confidence": 0.9,
                },
                {
                    "id": "u1-2026-05-18-work-progress",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "work-progress",
                    "title": "Work progress",
                    "source_chat_ids": ["raw-yesterday-line"],
                    "summary": {
                        "topic": "Reviewed implementation",
                        "self_feeling": "Focused.",
                        "other_feeling": "Collaborative.",
                        "outcome": "Compatibility removal was reviewed.",
                    },
                    "entity_ids": ["project-x"],
                    "confidence": 0.92,
                },
            ],
            "entity_patches": [],
            "profile_patch": None,
            "source_evaluations": [
                {
                    "chat_id": "raw-yesterday-discord",
                    "disposition": "used",
                    "reason": "Supports the morning episode.",
                },
                {
                    "chat_id": "raw-yesterday-line",
                    "disposition": "used",
                    "reason": "Supports the work episode.",
                },
            ],
            "evidence": {
                "notes": ["User mentioned project-x"],
            },
        }
        return Ok(GeneratedContent(contents=[json.dumps(payload)]))
