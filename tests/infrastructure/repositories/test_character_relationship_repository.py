"""Persistence tests for relationship evidence and snapshots."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from flow_res import is_err
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.relationship import (
    PersistedRelationshipSignal,
    RelationshipSignalKind,
    RelationshipSignalStatus,
)
from app.domain.repositories import RepositoryErrorType
from app.infrastructure.orm_models import ChatORM, UserORM
from app.infrastructure.orm_models.relationship_orm import (
    CharacterRelationshipORM,
    RelationshipSignalEventORM,
)
from app.infrastructure.repositories.character_relationship_repository import (
    CharacterRelationshipRepository,
)


@pytest.mark.anyio
async def test_provisional_signal_is_idempotent_and_replaces_changed_classification(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _seed(session, ["chat-1"])
        repository = CharacterRelationshipRepository(session)
        original = _signal(
            "original", "chat-1", RelationshipSignalKind.STRONG_POSITIVE, 3
        )
        repeated = await repository.record_provisional(original)
        assert not is_err(repeated)
        repeated = await repository.record_provisional(original)
        assert not is_err(repeated)
        assert repeated.value.affection == 3

        corrected = await repository.record_provisional(
            _signal("corrected", "chat-1", RelationshipSignalKind.POSITIVE, 1)
        )
        assert not is_err(corrected)
        assert corrected.value.affection == 1

        events = list(
            (await session.execute(select(RelationshipSignalEventORM))).scalars()
        )
        assert {event.id: event.status for event in events} == {
            "original": RelationshipSignalStatus.SUPERSEDED.value,
            "corrected": RelationshipSignalStatus.PROVISIONAL.value,
        }


@pytest.mark.anyio
async def test_reconciliation_corrects_confirmed_result_and_recalculates_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _seed(session, ["chat-1"])
        repository = CharacterRelationshipRepository(session)
        first = await repository.reconcile_confirmed(
            character_id="shirasagi-reina",
            user_id="u1",
            evaluated_chat_ids=["chat-1"],
            signals=[
                _signal(
                    "confirmed-positive",
                    "chat-1",
                    RelationshipSignalKind.STRONG_POSITIVE,
                    3,
                    status=RelationshipSignalStatus.CONFIRMED,
                )
            ],
        )
        assert not is_err(first)
        assert first.value.affection == 3

        corrected = await repository.reconcile_confirmed(
            character_id="shirasagi-reina",
            user_id="u1",
            evaluated_chat_ids=["chat-1", "chat-1"],
            signals=[
                _signal(
                    "confirmed-negative",
                    "chat-1",
                    RelationshipSignalKind.NEGATIVE,
                    -2,
                    status=RelationshipSignalStatus.CONFIRMED,
                )
            ],
        )
        assert not is_err(corrected)
        assert corrected.value.affection == 0

        events = list(
            (await session.execute(select(RelationshipSignalEventORM))).scalars()
        )
        assert (
            sum(
                event.status == RelationshipSignalStatus.CONFIRMED.value
                for event in events
            )
            == 1
        )


@pytest.mark.anyio
async def test_jst_daily_increase_cap_and_day_boundary_are_recalculated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    chat_ids = ["chat-1", "chat-2", "chat-3", "chat-4"]
    async with session_factory() as session:
        await _seed(session, chat_ids)
        repository = CharacterRelationshipRepository(session)
        before_midnight = datetime(2026, 1, 1, 14, 59, tzinfo=UTC)
        after_midnight = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
        affection = -1
        for index, chat_id in enumerate(chat_ids, start=1):
            result = await repository.record_provisional(
                _signal(
                    f"signal-{index}",
                    chat_id,
                    RelationshipSignalKind.STRONG_POSITIVE,
                    3,
                    observed_at=(before_midnight if index < 4 else after_midnight),
                )
            )
            assert not is_err(result)
            affection = result.value.affection
        assert affection == 8

        events = list(
            (
                await session.execute(
                    select(RelationshipSignalEventORM).order_by(
                        RelationshipSignalEventORM.id
                    )
                )
            ).scalars()
        )
        assert [event.applied_delta for event in events] == [3, 2, 0, 3]


@pytest.mark.anyio
async def test_relationships_are_isolated_by_character(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await _seed(session, ["chat-1", "chat-2"])
        repository = CharacterRelationshipRepository(session)
        reina = await repository.record_provisional(
            _signal("reina", "chat-1", RelationshipSignalKind.STRONG_POSITIVE, 3)
        )
        marina = await repository.record_provisional(
            _signal(
                "marina",
                "chat-2",
                RelationshipSignalKind.POSITIVE,
                1,
                character_id="kurose-marina",
            )
        )
        assert not is_err(reina)
        assert not is_err(marina)
        assert reina.value.affection == 3
        assert marina.value.affection == 1


@pytest.mark.anyio
async def test_optimistic_snapshot_version_conflict_is_reported(
    session_factory: async_sessionmaker[AsyncSession], mocker: Any
) -> None:
    async with session_factory() as session:
        await _seed(session, ["chat-1"])
        session.add(
            CharacterRelationshipORM(
                character_id="shirasagi-reina",
                user_id="u1",
                affection=0,
                version=2,
            )
        )
        await session.commit()
        repository = CharacterRelationshipRepository(session)
        stale = CharacterRelationshipORM(
            character_id="shirasagi-reina",
            user_id="u1",
            affection=0,
            version=1,
        )
        mocker.patch.object(
            repository,
            "_load_relationship",
            AsyncMock(return_value=stale),
        )

        result = await repository.record_provisional(
            _signal("signal-1", "chat-1", RelationshipSignalKind.POSITIVE, 1)
        )

        assert is_err(result)
        assert result.error.type is RepositoryErrorType.VERSION_CONFLICT


def _signal(
    signal_id: str,
    chat_id: str,
    kind: RelationshipSignalKind,
    delta: int,
    *,
    status: RelationshipSignalStatus = RelationshipSignalStatus.PROVISIONAL,
    character_id: str = "shirasagi-reina",
    observed_at: datetime = datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
) -> PersistedRelationshipSignal:
    return PersistedRelationshipSignal(
        id=signal_id,
        character_id=character_id,
        user_id="u1",
        kind=kind,
        status=status,
        confidence=0.9,
        proposed_delta=delta,
        reason="test evidence",
        source_chat_ids=[chat_id],
        observed_at=observed_at,
    )


async def _seed(session: AsyncSession, chat_ids: list[str]) -> None:
    session.add(UserORM(id="u1"))
    session.add_all(
        ChatORM(
            id=chat_id,
            character_id="shirasagi-reina",
            channel="discord",
            external_conversation_id="conversation",
            external_participant_id="participant",
            user_id="u1",
            accepted_sequence=index,
            role="user",
            message_content={"type": "TEXT", "payload": {"texts": [chat_id]}},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            channel_metadata={},
        )
        for index, chat_id in enumerate(chat_ids, start=1)
    )
    await session.commit()
