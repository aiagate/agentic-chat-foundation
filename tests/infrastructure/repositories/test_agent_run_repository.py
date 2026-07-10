"""State-transition tests for durable AgentRun persistence."""

from datetime import UTC, datetime, timedelta

import pytest
from flow_res import is_ok
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.contracts.messages.agent_run import AgentRunStatus
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.tool_contracts import ToolCall
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.repositories.agent_run_repository import AgentRunRepository


@pytest.mark.asyncio
async def test_conversation_serialization_and_multi_tool_join() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: SQLModel.metadata.create_all(
                sync_connection,
                tables=[
                    SQLModel.metadata.tables[name]
                    for name in (
                        "chats",
                        "conversation_coordinators",
                        "agent_runs",
                        "agent_tool_calls",
                    )
                ],
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with sessions() as session:
        session.add_all(
            [
                ChatORM(
                    id="01J00000000000000000000001", type="DISCORD", message_content={}
                ),
                ChatORM(
                    id="01J00000000000000000000002", type="DISCORD", message_content={}
                ),
            ]
        )
        repository = AgentRunRepository(session)
        first = await repository.start(
            conversation_key="character:DISCORD:guild:channel",
            source_chat_id="01J00000000000000000000001",
            character_id="character",
            user_id="user",
            chat_type=ChatType.DISCORD,
            guild_id="guild",
            channel_id="channel",
            max_turns=8,
        )
        second = await repository.start(
            conversation_key="character:DISCORD:guild:channel",
            source_chat_id="01J00000000000000000000002",
            character_id="character",
            user_id="user",
            chat_type=ChatType.DISCORD,
            guild_id="guild",
            channel_id="channel",
            max_turns=8,
        )
        assert is_ok(first) and first.value.run.status is AgentRunStatus.READY
        assert is_ok(second) and second.value.run.status is AgentRunStatus.QUEUED
        await session.commit()
        first_run_id = first.value.run.id
        second_run_id = second.value.run.id

    async with sessions() as session:
        repository = AgentRunRepository(session)
        claimed = await repository.claim_run(
            run_id=first_run_id,
            wake_sequence=1,
            now=now,
            lease_expires_at=now + timedelta(minutes=5),
        )
        assert is_ok(claimed) and claimed.value is not None
        stale = await repository.claim_run(
            run_id=first_run_id,
            wake_sequence=1,
            now=now,
            lease_expires_at=now + timedelta(minutes=5),
        )
        assert is_ok(stale) and stale.value is None
        lease = claimed.value.lease_token
        tools = await repository.add_tool_calls(
            run_id=first_run_id,
            lease_token=lease or "",
            tool_calls=[
                (
                    ToolCall(
                        tool_call_id="tool-1",
                        tool_name="web_search",
                        arguments={"query": "one"},
                    ),
                    "reenter",
                ),
                (
                    ToolCall(
                        tool_call_id="tool-2",
                        tool_name="memory.read",
                        arguments={"memory_id": "two"},
                    ),
                    "reenter",
                ),
            ],
            now=now,
        )
        assert is_ok(tools) and len(tools.value) == 2
        await session.commit()

    for index, tool_id in enumerate(("tool-1", "tool-2"), start=1):
        async with sessions() as session:
            repository = AgentRunRepository(session)
            tool_claim = await repository.claim_tool_call(
                run_id=first_run_id,
                tool_call_id=tool_id,
                attempt_count=0,
                now=now,
                lease_expires_at=now + timedelta(minutes=5),
            )
            assert is_ok(tool_claim) and tool_claim.value is not None
            applied = await repository.complete_tool_call(
                run_id=first_run_id,
                tool_call_id=tool_id,
                lease_token=tool_claim.value[1].lease_token or "",
                succeeded=True,
                result={"index": index},
                rendered_result=f"result {index}",
                error_code=None,
                error_message=None,
                now=now,
            )
            assert is_ok(applied)
            assert (applied.value is None) is (index == 1)
            await session.commit()

    async with sessions() as session:
        repository = AgentRunRepository(session)
        resumed = await repository.claim_run(
            run_id=first_run_id,
            wake_sequence=2,
            now=now,
            lease_expires_at=now + timedelta(minutes=5),
        )
        assert is_ok(resumed) and resumed.value is not None
        assert [item.rendered_text for item in resumed.value.tool_results] == [
            "result 1",
            "result 2",
        ]
        promoted = await repository.complete_run(
            run_id=first_run_id,
            lease_token=resumed.value.lease_token or "",
            now=now,
        )
        assert is_ok(promoted) and promoted.value is not None
        assert promoted.value.id == second_run_id
        assert promoted.value.status is AgentRunStatus.READY
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_run_lease_is_recovered_with_new_wakeup_sequence() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: SQLModel.metadata.create_all(
                sync_connection,
                tables=[
                    SQLModel.metadata.tables[name]
                    for name in (
                        "chats",
                        "conversation_coordinators",
                        "agent_runs",
                        "agent_tool_calls",
                    )
                ],
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessions() as session:
        session.add(
            ChatORM(id="01J00000000000000000000003", type="LINE", message_content={})
        )
        repository = AgentRunRepository(session)
        started = await repository.start(
            conversation_key="character:LINE:user",
            source_chat_id="01J00000000000000000000003",
            character_id="character",
            user_id="user",
            chat_type=ChatType.LINE,
            guild_id="LINE",
            channel_id="user",
            max_turns=8,
        )
        assert is_ok(started)
        claimed = await repository.claim_run(
            run_id=started.value.run.id,
            wake_sequence=1,
            now=now,
            lease_expires_at=now - timedelta(seconds=1),
        )
        assert is_ok(claimed) and claimed.value is not None
        await session.commit()

    async with sessions() as session:
        recovered = await AgentRunRepository(session).recover_due(now=now, limit=10)
        assert is_ok(recovered)
        assert len(recovered.value.runs) == 1
        assert recovered.value.runs[0].wake_sequence == 2
        assert recovered.value.runs[0].status is AgentRunStatus.READY
        await session.commit()
    await engine.dispose()
