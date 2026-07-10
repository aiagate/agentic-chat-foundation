"""Tests for transactional outbox writes through the application UoW."""

from typing import Any, cast

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.ports.unit_of_work import IUnitOfWork
from app.infrastructure.orm_models.outbox_message_orm import OutboxMessageORM


@pytest.mark.anyio
async def test_uow_commits_outbox_message(uow: IUnitOfWork) -> None:
    async with uow:
        event_id = uow.enqueue_event("example.created", {"value": 1})
        await uow.commit()

    async with uow:
        session = cast(AsyncSession, cast(Any, uow)._session)
        table = cast(Any, OutboxMessageORM).__table__
        message = (
            await session.execute(
                select(OutboxMessageORM).where(table.c.id == event_id)
            )
        ).scalar_one()

    assert message.payload["event_id"] == event_id
    assert message.topic == "example.created"


@pytest.mark.anyio
async def test_uow_rolls_back_outbox_message(uow: IUnitOfWork) -> None:
    with pytest.raises(RuntimeError, match="force rollback"):
        async with uow:
            uow.enqueue_event("example.created", {"value": 1})
            raise RuntimeError("force rollback")

    async with uow:
        session = cast(AsyncSession, cast(Any, uow)._session)
        count = await session.scalar(select(func.count()).select_from(OutboxMessageORM))

    assert count == 0
