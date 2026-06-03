"""SQLAlchemy implementation of chat history query."""

import logging
from typing import Any, Literal, cast

from flow_res import Err, Ok, Result
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.messages.chat_history import ChatHistoryItem
from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.repositories.interfaces import RepositoryError, RepositoryErrorType
from app.domain.value_objects.chat_type import ChatType
from app.infrastructure.orm_models.chat_orm import ChatORM

logger = logging.getLogger(__name__)


class SQLAlchemyChatHistoryQuery(IChatHistoryQuery):
    """SQLAlchemy implementation of chat history query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_recent_history(
        self,
        chat_type: ChatType,
        user_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        limit: int = 20,
    ) -> Result[list[ChatHistoryItem], RepositoryError]:
        """Get recent chat history for the given platform."""
        try:
            table = cast(Any, ChatORM).__table__
            conditions: list[Any] = [table.c.type == chat_type.to_primitive()]
            if user_id is not None:
                conditions.append(table.c.user_id == user_id)
            if chat_type is ChatType.DISCORD:
                if guild_id is not None:
                    conditions.append(table.c.discord_guild_id == guild_id)
                if channel_id is not None:
                    conditions.append(table.c.discord_channel_id == channel_id)
            elif chat_type is ChatType.LINE:
                if user_id is not None:
                    conditions.append(table.c.line_user_id == user_id)

            statement = (
                select(ChatORM)
                .where(*conditions)
                .order_by(desc(table.c.created_at), desc(table.c.id))
                .limit(limit)
            )
            result = await self._session.execute(statement)
            orm_items = list(result.scalars().all())
            orm_items.reverse()
            history_items = [
                _to_history_item(item) for item in orm_items if item.id is not None
            ]
            return Ok(history_items)
        except SQLAlchemyError as e:
            logger.exception("Database error occurred in chat history lookup")
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(e),
                )
            )


def _normalize_role(
    role: str | None,
) -> Literal["user", "assistant", "system"]:
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    if role == "system":
        return role
    return "user"


def _to_history_item(item: ChatORM) -> ChatHistoryItem:
    payload = item.message_content.get("payload")
    content = ""
    if isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            content = text
    return ChatHistoryItem(
        id=item.id or "",
        user_id=item.user_id,
        chat_type=ChatType.from_primitive(item.type).unwrap(),
        role=_normalize_role(item.role),
        content=content,
        occurred_at=item.created_at,
    )
