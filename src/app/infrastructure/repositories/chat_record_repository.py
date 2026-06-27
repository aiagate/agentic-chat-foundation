"""Repository for chat record writes."""

from __future__ import annotations

from typing import cast

from flow_res import Err, Ok, Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.chat import Chat
from app.domain.repositories import (
    IChatRecordRepository,
    RepositoryError,
    RepositoryErrorType,
)
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM


class ChatRecordRepository(IChatRecordRepository):
    """Persist chat records without exposing ORM details to use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        chat: Chat,
        *,
        user_id: str,
        role: str,
    ) -> Result[Chat, RepositoryError]:
        try:
            chat_orm = cast(ChatORM, ORMMappingRegistry.to_orm(chat))
            chat_orm.user_id = user_id
            chat_orm.role = role
            self._session.add(chat_orm)
            await self._session.flush()
            return Ok(cast(Chat, ORMMappingRegistry.from_orm(chat_orm)))
        except SQLAlchemyError as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )
