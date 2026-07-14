"""Repository for chat record writes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from flow_res import Err, Ok, Result
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from app.domain.repositories import (
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
        channel: str,
        external_conversation_id: str,
        external_participant_id: str,
        external_message_id: str | None,
        role: str,
        message_content: Mapping[str, object],
        channel_metadata: Mapping[str, object],
    ) -> Result[str, RepositoryError]:
        try:
            chat_orm = ChatORM(
                id=str(ULID()),
                channel=channel,
                external_conversation_id=external_conversation_id,
                external_participant_id=external_participant_id,
                external_message_id=external_message_id,
                role=role,
                message_content=dict(message_content),
                channel_metadata=dict(channel_metadata),
            )
            self._session.add(chat_orm)
            await self._session.flush()
            return Ok(chat_orm.id or "")
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
    ) -> Result[str | None, RepositoryError]:
        try:
            table = cast(Any, ChatORM).__table__
            result = await self._session.execute(
                select(table.c.id).where(
                    table.c.channel == channel,
                    table.c.external_message_id == external_message_id,
                )
            )
            return Ok(result.scalar_one_or_none())
        except SQLAlchemyError as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )
