"""Tests for the memory sleep use case."""

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
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_context import MemoryProfile
from app.contracts.messages.tool_contracts import ToolDefinition
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.queries.raw_chat_log_query import MemorySleepSourceItem
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.memory.store import FilesystemMemoryStore
from app.infrastructure.orm_models import ChatORM
from app.infrastructure.queries.memory_sleep_query_service import (
    MemorySleepQueryService,
    MemorySleepTarget,
)
from app.infrastructure.services.memory_consolidation import MemoryConsolidationService
from app.infrastructure.services.memory_semantic_extraction import (
    MemorySemanticExtractionService,
)
from app.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from app.usecases.memory.run_memory_sleep import (
    RunMemorySleepCommand,
    RunMemorySleepHandler,
)


class _FakeAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AGENT_PROFILE_BUNDLE


AGENT_PROFILE_BUNDLE = AgentProfileBundle(
    profile=MemoryProfile(user_id="ai"),
    character=CharacterDefinition(
        character_id="jondue",
        relationship_entity_id="relationship:jondue",
        relationship_entity_label="Relationship with Jon Due",
    ),
    persona_context="Persona Contract:\n- test persona",
    relationship_entity_id="relationship:jondue",
    relationship_entity_label="Relationship with Jon Due",
    relationship_entity_type="relationship",
    relationship_tag="agent-growth",
)


@pytest.mark.anyio
async def test_run_memory_sleep_handler_invokes_consolidation_service(
    mocker: Any,
) -> None:
    """Test that the sleep command delegates to the consolidation port."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    source_repository = mocker.Mock()
    source_repository.mark_consolidated = AsyncMock(return_value=Ok(2))
    uow.GetMemoryConsolidatedChatSourceRepository = mocker.Mock(
        return_value=source_repository
    )
    uow.commit = AsyncMock(return_value=Ok(None))
    memory_sleep_query_service = mocker.Mock(spec=MemorySleepQueryService)
    memory_sleep_query_service.list_pending_targets = AsyncMock(
        return_value=[
            MemorySleepTarget(
                user_id="u1",
                day=datetime(2026, 5, 18).date(),
                raw_logs=[
                    _memory_sleep_source_item(
                        "raw-1",
                        chat_type=ChatType.DISCORD,
                        created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    ),
                    _memory_sleep_source_item(
                        "raw-2",
                        chat_type=ChatType.LINE,
                        created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    ),
                ],
            )
        ]
    )
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.consolidate_chat_logs = AsyncMock(return_value=2)

    handler = RunMemorySleepHandler(
        memory_store,
        uow,
        consolidation_service,
        memory_sleep_query_service,
    )

    result = await handler.handle(
        RunMemorySleepCommand(reference_time=datetime(2026, 5, 19, tzinfo=UTC))
    )

    assert not is_err(result)
    assert result.value.consolidated_count == 2
    assert uow.GetRawChatLogQuery.call_count == 1
    memory_sleep_query_service.list_pending_targets.assert_awaited_once_with(
        raw_chat_log_query,
        reference_time=datetime(2026, 5, 19, tzinfo=UTC),
    )
    consolidation_stub = cast(Any, consolidation_service.consolidate_chat_logs)
    consolidation_stub.assert_awaited_once()
    await_args = consolidation_stub.await_args
    assert await_args is not None
    assert await_args.args == (memory_store,)
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
async def test_run_memory_sleep_handler_reports_failures(
    mocker: Any,
) -> None:
    """Test that consolidation failures are surfaced as use case errors."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    memory_sleep_query_service = mocker.Mock(spec=MemorySleepQueryService)
    memory_sleep_query_service.list_pending_targets = AsyncMock(
        return_value=[
            MemorySleepTarget(
                user_id="u1",
                day=datetime(2026, 5, 18).date(),
                raw_logs=[
                    _memory_sleep_source_item(
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

    handler = RunMemorySleepHandler(
        memory_store,
        uow,
        consolidation_service,
        memory_sleep_query_service,
    )

    result = await handler.handle(RunMemorySleepCommand())

    assert is_err(result)
    assert uow.GetRawChatLogQuery.call_count == 1


@pytest.mark.anyio
async def test_run_memory_sleep_handler_does_not_use_run_repository(
    mocker: Any,
) -> None:
    """Test that the handler no longer depends on a run repository."""

    memory_store = mocker.Mock(spec=IMemoryStore)
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    raw_chat_log_query = mocker.Mock()
    uow.GetRawChatLogQuery = mocker.Mock(return_value=raw_chat_log_query)
    memory_sleep_query_service = mocker.Mock(spec=MemorySleepQueryService)
    memory_sleep_query_service.list_pending_targets = AsyncMock(return_value=[])
    consolidation_service = mocker.Mock(spec=IMemoryConsolidationService)
    consolidation_service.consolidate_chat_logs = AsyncMock(return_value=0)

    handler = RunMemorySleepHandler(
        memory_store,
        uow,
        consolidation_service,
        memory_sleep_query_service,
    )

    result = await handler.handle(RunMemorySleepCommand())

    assert not is_err(result)
    assert result.value.consolidated_count == 0
    consolidation_service.consolidate_chat_logs.assert_not_awaited()


@pytest.mark.anyio
async def test_run_memory_sleep_handler_consolidates_sqlite_raw_logs(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """End-to-end sleep run should read SQLite raw logs and write memory docs."""

    await _seed_raw_chat_logs(session_factory)

    memory_store = FilesystemMemoryStore(tmp_path / "memory")
    uow = SQLAlchemyUnitOfWork(session_factory)
    memory_sleep_query_service = MemorySleepQueryService()
    handler = RunMemorySleepHandler(
        memory_store,
        uow,
        MemoryConsolidationService(
            semantic_extraction_service=MemorySemanticExtractionService(
                _FakeAIService(),
                _FakeAgentProfileService(),
            ),
            agent_profile_service=_FakeAgentProfileService(),
        ),
        memory_sleep_query_service,
    )

    result = await handler.handle(
        RunMemorySleepCommand(reference_time=datetime(2026, 5, 19, tzinfo=UTC))
    )

    assert not is_err(result)
    assert result.value.consolidated_count == 2

    morning = memory_store.read_document(
        memory_store.section_timeline_path(
            user_id="u1",
            day=datetime(2026, 5, 18).date(),
            section_slug="morning-routine",
        ),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    work = memory_store.read_document(
        memory_store.section_timeline_path(
            user_id="u1",
            day=datetime(2026, 5, 18).date(),
            section_slug="work-progress",
        ),
        expected_memory_type="timeline",
        expected_user_id="u1",
    )
    assert morning.front_matter["timeline_type"] == "section_summary"
    assert morning.front_matter["memory_id"] == "timeline:u1-2026-05-18-morning-routine"
    assert morning.front_matter["manifest_title"] == "Morning routine"
    assert (
        morning.front_matter["manifest_summary"]
        == "Started the day early | The early start was noted."
    )
    assert morning.front_matter["section_slug"] == "morning-routine"
    assert morning.front_matter["summary_of"] == [
        "raw-yesterday-discord",
        "raw-yesterday-line",
    ]
    assert "Started the day early" in morning.body
    assert "Felt a little sleepy." in morning.body
    assert "Source Chat IDs" not in morning.body
    assert "Evidence" not in morning.body
    assert work.front_matter["section_slug"] == "work-progress"
    assert work.front_matter["memory_id"] == "timeline:u1-2026-05-18-work-progress"
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
    """Insert deterministic raw chat logs into SQLite for sleep tests."""

    async with session_factory() as session:
        session.add_all(
            [
                ChatORM(
                    id="raw-yesterday-discord",
                    type=ChatType.DISCORD.to_primitive(),
                    user_id="u1",
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {
                            "text": "Yesterday should be consolidated.",
                        },
                    },
                    version=0,
                    created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
                    discord_guild_id="guild-1",
                    discord_channel_id="channel-1",
                ),
                ChatORM(
                    id="raw-yesterday-line",
                    type=ChatType.LINE.to_primitive(),
                    user_id="u1",
                    role="assistant",
                    message_content={
                        "type": "TEXT",
                        "payload": {
                            "text": "Daily summary should include raw SQL logs.",
                        },
                    },
                    version=0,
                    created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
                    line_user_id="line-user-1",
                ),
                ChatORM(
                    id="raw-today-discord",
                    type=ChatType.DISCORD.to_primitive(),
                    user_id="u1",
                    role="user",
                    message_content={
                        "type": "TEXT",
                        "payload": {"text": "Today should remain pending."},
                    },
                    version=0,
                    created_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 5, 19, 10, 0, tzinfo=UTC),
                    discord_guild_id="guild-1",
                    discord_channel_id="channel-1",
                ),
            ]
        )
        await session.commit()


def _memory_sleep_source_item(
    raw_id: str,
    *,
    chat_type: ChatType,
    created_at: datetime,
) -> MemorySleepSourceItem:
    return MemorySleepSourceItem(
        id=raw_id,
        user_id="u1",
        role="user",
        chat_type=chat_type,
        message_content={"payload": {"text": raw_id}},
        created_at=created_at,
    )


class _FakeAIService(IAIService):
    async def generate_content(
        self,
        prompt: str,
        history: list[ChatHistoryItem],
        system_instruction: str | None = None,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> Result[GeneratedContent, AIServiceError]:
        del prompt, history, system_instruction, tool_definitions
        payload = {
            "sections": [
                {
                    "id": "u1-2026-05-18-morning-routine",
                    "user_id": "u1",
                    "day": "2026-05-18",
                    "section_slug": "morning-routine",
                    "title": "Morning routine",
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
            "timeline_patch": None,
            "entity_patches": [],
            "profile_patch": None,
            "evidence": {
                "notes": ["User mentioned project-x"],
            },
        }
        return Ok(GeneratedContent(contents=[json.dumps(payload)]))
