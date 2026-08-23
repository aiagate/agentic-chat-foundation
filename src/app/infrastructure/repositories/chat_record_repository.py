"""Repository for chat record writes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from flow_res import Err, Ok, Result, is_err
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.domain.repositories import (
    ChatRecordReference,
    IChatRecordRepository,
    RepositoryError,
    RepositoryErrorType,
)
from app.infrastructure.orm_models.chat_orm import ChatORM


class ChatRecordRepository(IChatRecordRepository):
    """Persist chat records without exposing ORM details to use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_message(
        self,
        *,
        character_id: str,
        user_id: str,
        channel: str,
        external_conversation_id: str,
        external_participant_id: str,
        external_message_id: str | None,
        role: str,
        message_content: Mapping[str, object],
        channel_metadata: Mapping[str, object],
    ) -> Result[ChatRecordReference, RepositoryError]:
        try:
            accepted_sequence = await _next_sqlite_order_key(self._session)
            table = cast(Any, ChatORM).__table__
            values: dict[str, object] = {
                "id": str(ULID()),
                "character_id": character_id,
                "channel": channel,
                "external_conversation_id": external_conversation_id,
                "external_participant_id": external_participant_id,
                "user_id": user_id,
                "external_message_id": external_message_id,
                "role": role,
                "message_content": dict(message_content),
                "channel_metadata": dict(channel_metadata),
            }
            if accepted_sequence is not None:
                values["accepted_sequence"] = accepted_sequence
            dialect_name = self._session.bind.dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(table).values(**values)
            elif dialect_name == "sqlite":
                statement = sqlite_insert(table).values(**values)
            else:
                # The application currently supports PostgreSQL and SQLite.
                # Keep a clear fallback for other SQLAlchemy dialects, even
                # though they cannot provide the same atomic conflict path.
                chat_orm = ChatORM(**cast(Any, values))
                self._session.add(chat_orm)
                await self._session.flush()
                await self._session.refresh(
                    chat_orm,
                    attribute_names=["accepted_sequence"],
                )
                return Ok(
                    ChatRecordReference(
                        message_id=chat_orm.id or "",
                        user_id=user_id,
                        order_key=int(chat_orm.accepted_sequence or 0),
                    )
                )

            statement = statement.on_conflict_do_nothing(
                index_elements=[table.c.channel, table.c.external_message_id]
            )
            result = await self._session.execute(
                statement.returning(
                    table.c.id,
                    table.c.user_id,
                    table.c.accepted_sequence,
                )
            )
            inserted = result.first()
            if inserted is None:
                if not external_message_id:
                    raise RuntimeError("Message insert did not return a new row")
                existing = await self.find_by_external_message_id(
                    channel=channel,
                    external_message_id=external_message_id,
                )
                if is_err(existing):
                    return existing
                if existing.value is None:
                    raise RuntimeError(
                        "Message conflict occurred but the existing row could not be read"
                    )
                return Ok(
                    ChatRecordReference(
                        message_id=existing.value.message_id,
                        user_id=existing.value.user_id,
                        order_key=existing.value.order_key,
                        is_new=False,
                    )
                )
            return Ok(
                ChatRecordReference(
                    message_id=str(inserted.id),
                    user_id=str(inserted.user_id),
                    order_key=int(inserted.accepted_sequence or 0),
                )
            )
        except SQLAlchemyError as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )

    async def find_by_external_message_id(
        self,
        *,
        channel: str,
        external_message_id: str,
    ) -> Result[ChatRecordReference | None, RepositoryError]:
        try:
            table = cast(Any, ChatORM).__table__
            result = await self._session.execute(
                select(
                    table.c.id,
                    table.c.user_id,
                    table.c.accepted_sequence,
                ).where(
                    table.c.channel == channel,
                    table.c.external_message_id == external_message_id,
                )
            )
            row = result.one_or_none()
            if row is None:
                return Ok(None)
            return Ok(
                ChatRecordReference(
                    message_id=str(row.id),
                    user_id=str(row.user_id),
                    order_key=int(row.accepted_sequence),
                )
            )
        except SQLAlchemyError as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )


async def _next_sqlite_order_key(session: AsyncSession) -> int | None:
    """Supply the non-PostgreSQL test adapter with the same ordering contract."""

    if session.bind.dialect.name != "sqlite":
        return None
    table = cast(Any, ChatORM).__table__
    result = await session.execute(
        select(func.coalesce(func.max(table.c.accepted_sequence), 0) + 1)
    )
    return int(result.scalar_one())
