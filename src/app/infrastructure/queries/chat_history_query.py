"""SQLAlchemy implementation of chat history query."""

import logging
from typing import Any, Literal, cast

from flow_res import Err, Ok, Result
from sqlalchemy import desc, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.messages.chat_history import ChatHistoryItem, ChatHistoryWindow
from app.contracts.messages.chat_type import ChatType
from app.domain.queries.chat_history_query import IChatHistoryQuery
from app.domain.repositories.interfaces import RepositoryError, RepositoryErrorType
from app.domain.value_objects.conversation_scope import ConversationScope
from app.domain.value_objects.message_content import render_message_content_text
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.orm_models.memory_consolidated_chat_source_orm import (
    MemoryConsolidatedChatSourceORM,
)

logger = logging.getLogger(__name__)


class SQLAlchemyChatHistoryQuery(IChatHistoryQuery):
    """SQLAlchemy implementation of chat history query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_recent_history(
        self,
        chat_type: ChatType,
        *,
        character_id: str,
        user_id: str,
        external_conversation_id: str,
        before_order_key: int | None = None,
        limit: int = 20,
    ) -> Result[ChatHistoryWindow, RepositoryError]:
        """Get recent chat history for the given platform."""
        try:
            scope = ConversationScope(
                user_id=user_id,
                character_id=character_id,
                channel=chat_type.to_primitive(),
                external_conversation_id=external_conversation_id,
            )
            table = cast(Any, ChatORM).__table__
            conditions: list[Any] = [
                table.c.channel == scope.channel,
                table.c.character_id == scope.character_id,
                table.c.user_id == scope.user_id,
                table.c.external_conversation_id == scope.external_conversation_id,
            ]
            if before_order_key is not None:
                # This key is allocated by the database at acceptance time,
                # so a later webhook cannot enter an earlier turn's window.
                conditions.append(table.c.accepted_sequence <= before_order_key)

            statement = (
                select(ChatORM)
                .where(
                    *conditions,
                    ~exists().where(
                        MemoryConsolidatedChatSourceORM.chat_id == table.c.id
                    ),
                )
                .order_by(desc(table.c.created_at), desc(table.c.id))
                .limit(limit)
            )
            result = await self._session.execute(statement)
            orm_items = list(result.scalars().all())
            orm_items.reverse()
            history_items = [
                _to_history_item(item) for item in orm_items if item.id is not None
            ]
            boundary_statement = select(func.max(table.c.created_at)).where(
                *conditions,
                exists().where(MemoryConsolidatedChatSourceORM.chat_id == table.c.id),
            )
            boundary_result = await self._session.execute(boundary_statement)
            return Ok(
                ChatHistoryWindow(
                    items=history_items,
                    memory_boundary_at=boundary_result.scalar_one_or_none(),
                )
            )
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
        text = render_message_content_text(payload)
        if isinstance(text, str):
            content = text
    return ChatHistoryItem(
        id=item.id or "",
        user_id=item.user_id,
        chat_type=ChatType.from_primitive(item.channel).unwrap(),
        role=_normalize_role(item.role),
        content=content,
        occurred_at=item.created_at,
    )
