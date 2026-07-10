"""SQLAlchemy query for one agent turn's persisted context."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from flow_res import Err, Ok, Result, is_err
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.agent_turn_context import AgentTurnContext
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.chat_type import ChatType
from app.contracts.messages.conversation_context import ConversationContext
from app.contracts.ports.agent_turn_context_query import (
    AgentTurnContextQueryError,
    IAgentTurnContextQuery,
)
from app.domain.value_objects.message_content import render_message_content_text
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.queries.chat_history_query import SQLAlchemyChatHistoryQuery

_SESSION_GAP_THRESHOLD = timedelta(hours=24)


class SQLAlchemyAgentTurnContextQuery(IAgentTurnContextQuery):
    """Resolve agent-turn input within one short-lived database session."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load(
        self,
        *,
        chat_id: str,
        provided_prompt: str | None,
        chat_type: ChatType,
        user_id: str,
        guild_id: str,
        channel_id: str,
    ) -> Result[AgentTurnContext, AgentTurnContextQueryError]:
        try:
            async with self._session_factory() as session:
                prompt_result = await self._resolve_prompt(
                    session,
                    chat_id=chat_id,
                    provided_prompt=provided_prompt,
                )
                if is_err(prompt_result):
                    return prompt_result

                history_result = await SQLAlchemyChatHistoryQuery(
                    session
                ).get_recent_history(
                    chat_type,
                    user_id=user_id,
                    guild_id=guild_id if chat_type is ChatType.DISCORD else None,
                    channel_id=channel_id if chat_type is ChatType.DISCORD else None,
                    limit=20,
                )
                if is_err(history_result):
                    return Err(
                        AgentTurnContextQueryError("Failed to retrieve chat history")
                    )

                history_window = history_result.value
                session_history, boundary = latest_session_window(
                    history_window.items,
                    memory_boundary_at=history_window.memory_boundary_at,
                )
                prompt = prompt_result.value
                return Ok(
                    AgentTurnContext(
                        prompt=prompt,
                        recent_history=_trim_duplicate_prompt(session_history, prompt),
                        conversation=_conversation_context(
                            session_history,
                            boundary=boundary,
                            chat_type=chat_type,
                            user_id=user_id,
                            guild_id=guild_id,
                            channel_id=channel_id,
                        ),
                    )
                )
        except SQLAlchemyError as exc:
            return Err(AgentTurnContextQueryError(str(exc)))

    async def _resolve_prompt(
        self,
        session: AsyncSession,
        *,
        chat_id: str,
        provided_prompt: str | None,
    ) -> Result[str, AgentTurnContextQueryError]:
        normalized_prompt = _normalize_text(provided_prompt)
        if normalized_prompt:
            return Ok(normalized_prompt)

        table = cast(Any, ChatORM).__table__
        result = await session.execute(select(ChatORM).where(table.c.id == chat_id))
        chat = result.scalar_one_or_none()
        if chat is None:
            return Err(AgentTurnContextQueryError("Failed to load chat message"))
        payload = chat.message_content.get("payload")
        text = (
            render_message_content_text(payload) if isinstance(payload, dict) else None
        )
        prompt = _normalize_text(text)
        if not prompt:
            return Err(
                AgentTurnContextQueryError(
                    "Saved chat message does not contain text content"
                )
            )
        return Ok(prompt)


def latest_session_window(
    history: Sequence[ChatHistoryItem],
    *,
    memory_boundary_at: datetime | None,
) -> tuple[list[ChatHistoryItem], tuple[datetime, datetime, int] | None]:
    """Return messages from the latest session and its boundary metadata."""
    if not history:
        return [], None

    start_index = 0
    boundary: tuple[datetime, datetime, int] | None = None
    first_at = history[0].occurred_at
    if memory_boundary_at is not None and first_at is not None:
        current_utc = _as_utc(first_at)
        previous_utc = _as_utc(memory_boundary_at)
        gap = max(current_utc - previous_utc, timedelta())
        boundary = (current_utc, previous_utc, int(gap.total_seconds() // 60))
    for index in range(1, len(history)):
        previous_at = history[index - 1].occurred_at
        current_at = history[index].occurred_at
        if previous_at is None or current_at is None:
            continue
        previous_utc = _as_utc(previous_at)
        current_utc = _as_utc(current_at)
        gap = current_utc - previous_utc
        if gap > _SESSION_GAP_THRESHOLD:
            start_index = index
            boundary = (current_utc, previous_utc, int(gap.total_seconds() // 60))
    return list(history[start_index:]), boundary


def _trim_duplicate_prompt(
    history: Sequence[ChatHistoryItem],
    prompt: str,
) -> list[ChatHistoryItem]:
    if not history:
        return []
    if history[-1].role != "user":
        return list(history)
    if _normalize_text(history[-1].content) != _normalize_text(prompt):
        return list(history)
    return list(history[:-1])


def _conversation_context(
    history: Sequence[ChatHistoryItem],
    *,
    boundary: tuple[datetime, datetime, int] | None,
    chat_type: ChatType,
    user_id: str,
    guild_id: str,
    channel_id: str,
) -> ConversationContext:
    scope = f"LINE user_id={user_id}"
    if chat_type is ChatType.DISCORD:
        scope = f"DISCORD guild_id={guild_id} channel_id={channel_id} user_id={user_id}"
    return ConversationContext(
        chat_scope=scope,
        current_time=datetime.now(UTC),
        timezone="UTC",
        observed_message_count=len(history),
        has_session_boundary=boundary is not None,
        current_session_started_at=boundary[0] if boundary is not None else None,
        previous_message_at=boundary[1] if boundary is not None else None,
        gap_minutes=boundary[2] if boundary is not None else None,
    )


def _normalize_text(value: str | None) -> str:
    return "" if value is None else " ".join(value.split())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
