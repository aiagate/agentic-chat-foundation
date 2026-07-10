"""Tests for SQLAlchemy outbox claiming and updates."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from flow_res import is_err
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.ports.unit_of_work import IUnitOfWork
from app.infrastructure.orm_models.outbox_message_orm import OutboxMessageORM
from app.infrastructure.stores.outbox_store import SQLAlchemyOutboxStore


@pytest.mark.anyio
async def test_outbox_store_claims_and_marks_message_published(
    uow: IUnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime(2026, 6, 28, tzinfo=UTC)
    async with uow:
        event_id = uow.enqueue_event("example.created", {"value": 1})
        await uow.commit()

    store = SQLAlchemyOutboxStore(session_factory)
    claim_result = await store.claim_pending(limit=10, now=now)
    assert not is_err(claim_result)
    message = claim_result.value[0]
    assert message.id == event_id
    assert message.claim_token

    mark_result = await store.mark_published(
        message.id,
        message.claim_token,
        published_at=now,
    )
    assert not is_err(mark_result)

    async with session_factory() as session:
        table = cast(Any, OutboxMessageORM).__table__
        row = (
            await session.execute(
                select(OutboxMessageORM).where(table.c.id == event_id)
            )
        ).scalar_one()
    assert row.published_at is not None
    assert row.claim_token is None
