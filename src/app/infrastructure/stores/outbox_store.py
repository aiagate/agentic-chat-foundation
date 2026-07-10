"""SQLAlchemy transactional outbox delivery store."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from flow_res import Err, Ok, Result
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.outbox_message import OutboxMessage
from app.contracts.ports.outbox_store import IOutboxStore, OutboxStoreError
from app.infrastructure.orm_models.outbox_message_orm import OutboxMessageORM

_CLAIM_LEASE = timedelta(minutes=5)


class SQLAlchemyOutboxStore(IOutboxStore):
    """Claim and update outbox rows using short transactions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim_pending(
        self,
        *,
        limit: int,
        now: datetime,
    ) -> Result[list[OutboxMessage], OutboxStoreError]:
        table = cast(Any, OutboxMessageORM).__table__
        claim_token = str(uuid4())
        try:
            async with self._session_factory() as session:
                statement = (
                    select(OutboxMessageORM)
                    .where(
                        table.c.published_at.is_(None),
                        or_(
                            table.c.next_attempt_at.is_(None),
                            table.c.next_attempt_at <= now,
                        ),
                        or_(
                            table.c.claim_token.is_(None),
                            table.c.claimed_at < now - _CLAIM_LEASE,
                        ),
                    )
                    .order_by(table.c.created_at, table.c.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                rows = list((await session.execute(statement)).scalars().all())
                for row in rows:
                    row.claim_token = claim_token
                    row.claimed_at = now
                    row.attempt_count += 1
                await session.commit()
                return Ok(
                    [
                        OutboxMessage(
                            id=row.id,
                            topic=row.topic,
                            payload=dict(row.payload),
                            created_at=row.created_at or now,
                            attempt_count=row.attempt_count,
                            claim_token=claim_token,
                        )
                        for row in rows
                    ]
                )
        except SQLAlchemyError as exc:
            return Err(OutboxStoreError(str(exc)))

    async def mark_published(
        self,
        message_id: str,
        claim_token: str,
        *,
        published_at: datetime,
    ) -> Result[None, OutboxStoreError]:
        return await self._update_claimed(
            message_id,
            claim_token,
            values={
                "published_at": published_at,
                "claimed_at": None,
                "claim_token": None,
                "last_error": None,
            },
        )

    async def mark_failed(
        self,
        message_id: str,
        claim_token: str,
        *,
        error: str,
        next_attempt_at: datetime,
    ) -> Result[None, OutboxStoreError]:
        return await self._update_claimed(
            message_id,
            claim_token,
            values={
                "next_attempt_at": next_attempt_at,
                "claimed_at": None,
                "claim_token": None,
                "last_error": error,
            },
        )

    async def _update_claimed(
        self,
        message_id: str,
        claim_token: str,
        *,
        values: dict[str, object],
    ) -> Result[None, OutboxStoreError]:
        table = cast(Any, OutboxMessageORM).__table__
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    update(OutboxMessageORM)
                    .where(
                        and_(
                            table.c.id == message_id,
                            table.c.claim_token == claim_token,
                        )
                    )
                    .values(**values)
                )
                if cast(Any, result).rowcount != 1:
                    await session.rollback()
                    return Err(OutboxStoreError("Outbox claim is no longer owned"))
                await session.commit()
                return Ok(None)
        except SQLAlchemyError as exc:
            return Err(OutboxStoreError(str(exc)))
