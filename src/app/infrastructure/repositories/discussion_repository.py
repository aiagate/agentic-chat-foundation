"""SQLAlchemy persistence for one bot's local Discord discussion state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ulid import ULID

from app.contracts.messages.discussion import (
    AgentTurnDecision,
    AgentTurnDisposition,
    AgentTurnRecord,
    AutonomousTopicActivity,
    AutonomousTopicTurnRecord,
    DiscussionActivity,
    DiscussionAuthorKind,
    DiscussionHistoryItem,
    IncomingDiscussionMessage,
    ObservedDiscussionMessage,
    PrivateReflection,
)
from app.contracts.ports.discussion import (
    IAutonomousTopicRepository,
    IDiscussionRepository,
)
from app.infrastructure.orm_models.discussion_orm import (
    AgentTurnORM,
    AutonomousTopicTurnORM,
    DiscussionMessageORM,
)


class SQLAlchemyDiscussionRepository(IDiscussionRepository, IAutonomousTopicRepository):
    """Keep public Discord observations and private turns in a local database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def observe(
        self, message: IncomingDiscussionMessage
    ) -> ObservedDiscussionMessage:
        async with self._session_factory() as session:
            existing = await self._find_by_external_id(
                session, message.external_message_id
            )
            if existing is not None:
                return _observed(existing, is_new=False)
            row = DiscussionMessageORM(
                id=str(ULID()),
                external_message_id=message.external_message_id,
                guild_id=message.guild_id,
                channel_id=message.channel_id,
                author_external_id=message.author_external_id,
                author_display_name=message.author_display_name,
                author_kind=message.author_kind.value,
                message_text=message.text.strip(),
                mentioned_self=message.mentioned_self,
                recovered=message.recovered,
                occurred_at=_as_utc(message.occurred_at),
            )
            session.add(row)
            await session.commit()
            return _observed(row, is_new=True)

    async def append_self_message(
        self,
        *,
        guild_id: str,
        channel_id: str,
        external_message_id: str,
        author_external_id: str,
        author_display_name: str,
        text: str,
        occurred_at: datetime,
    ) -> ObservedDiscussionMessage:
        return await self.observe(
            IncomingDiscussionMessage(
                external_message_id=external_message_id,
                guild_id=guild_id,
                channel_id=channel_id,
                author_external_id=author_external_id,
                author_display_name=author_display_name,
                author_kind=DiscussionAuthorKind.SELF,
                text=text,
                occurred_at=occurred_at,
            )
        )

    async def recent_history(
        self,
        *,
        guild_id: str,
        channel_id: str,
        before_message_id: str,
        limit: int,
    ) -> list[DiscussionHistoryItem]:
        async with self._session_factory() as session:
            current = await session.get(DiscussionMessageORM, before_message_id)
            if current is None:
                return []
            table = cast(Any, DiscussionMessageORM).__table__
            result = await session.execute(
                select(DiscussionMessageORM)
                .where(
                    table.c.guild_id == guild_id,
                    table.c.channel_id == channel_id,
                    table.c.id != before_message_id,
                    table.c.occurred_at <= current.occurred_at,
                )
                .order_by(desc(table.c.occurred_at), desc(table.c.id))
                .limit(limit)
            )
            rows = list(result.scalars().all())
            rows.reverse()
            return [_history_item(row) for row in rows]

    async def latest_history(
        self,
        *,
        guild_id: str,
        channel_id: str,
        limit: int,
    ) -> list[DiscussionHistoryItem]:
        async with self._session_factory() as session:
            table = cast(Any, DiscussionMessageORM).__table__
            result = await session.execute(
                select(DiscussionMessageORM)
                .where(
                    table.c.guild_id == guild_id,
                    table.c.channel_id == channel_id,
                )
                .order_by(desc(table.c.occurred_at), desc(table.c.id))
                .limit(limit)
            )
            rows = list(result.scalars().all())
            rows.reverse()
            return [_history_item(row) for row in rows]

    async def recent_reflections(
        self,
        *,
        character_id: str,
        channel_id: str,
        limit: int,
    ) -> list[PrivateReflection]:
        async with self._session_factory() as session:
            table = cast(Any, AgentTurnORM).__table__
            result = await session.execute(
                select(AgentTurnORM)
                .where(
                    table.c.character_id == character_id,
                    table.c.channel_id == channel_id,
                    table.c.private_reflection.is_not(None),
                )
                .order_by(desc(table.c.created_at), desc(table.c.id))
                .limit(limit)
            )
            topic_table = cast(Any, AutonomousTopicTurnORM).__table__
            topic_result = await session.execute(
                select(AutonomousTopicTurnORM)
                .where(
                    topic_table.c.character_id == character_id,
                    topic_table.c.channel_id == channel_id,
                    topic_table.c.private_reflection.is_not(None),
                )
                .order_by(desc(topic_table.c.created_at), desc(topic_table.c.id))
                .limit(limit)
            )
            rows = [
                (row.created_at or datetime.min, row.private_reflection)
                for row in result.scalars().all()
            ]
            rows.extend(
                (row.created_at or datetime.min, row.private_reflection)
                for row in topic_result.scalars().all()
            )
            rows.sort(key=lambda item: _as_utc(item[0]), reverse=True)
            selected = rows[:limit]
            selected.reverse()
            return [
                PrivateReflection.model_validate(reflection)
                for _, reflection in selected
                if reflection is not None
            ]

    async def messages_after(
        self,
        *,
        guild_id: str,
        channel_id: str,
        after_message_id: str,
        limit: int,
    ) -> list[ObservedDiscussionMessage]:
        """Return public messages observed after one pending trigger."""

        async with self._session_factory() as session:
            current = await session.get(DiscussionMessageORM, after_message_id)
            if current is None:
                return []
            table = cast(Any, DiscussionMessageORM).__table__
            result = await session.execute(
                select(DiscussionMessageORM)
                .where(
                    table.c.guild_id == guild_id,
                    table.c.channel_id == channel_id,
                    or_(
                        table.c.occurred_at > current.occurred_at,
                        and_(
                            table.c.occurred_at == current.occurred_at,
                            table.c.id > after_message_id,
                        ),
                    ),
                )
                .order_by(table.c.occurred_at, table.c.id)
                .limit(limit)
            )
            return [_observed(row, is_new=False) for row in result.scalars().all()]

    async def activity(
        self,
        *,
        channel_id: str,
        character_id: str,
        window_started_at: datetime,
    ) -> DiscussionActivity:
        async with self._session_factory() as session:
            message_table = cast(Any, DiscussionMessageORM).__table__
            recent_result = await session.execute(
                select(message_table.c.author_kind)
                .where(message_table.c.channel_id == channel_id)
                .order_by(desc(message_table.c.occurred_at), desc(message_table.c.id))
                .limit(50)
            )
            consecutive_bot_messages = 0
            for kind in recent_result.scalars():
                if kind == DiscussionAuthorKind.HUMAN.value:
                    break
                consecutive_bot_messages += 1

            turn_table = cast(Any, AgentTurnORM).__table__
            last_result = await session.execute(
                select(func.max(turn_table.c.updated_at)).where(
                    turn_table.c.channel_id == channel_id,
                    turn_table.c.character_id == character_id,
                    turn_table.c.disposition == AgentTurnDisposition.PUBLISHED.value,
                )
            )
            count_result = await session.execute(
                select(func.count(turn_table.c.id)).where(
                    turn_table.c.channel_id == channel_id,
                    turn_table.c.character_id == character_id,
                    turn_table.c.disposition == AgentTurnDisposition.PUBLISHED.value,
                    turn_table.c.updated_at >= _as_utc(window_started_at),
                )
            )
            return DiscussionActivity(
                consecutive_bot_messages=consecutive_bot_messages,
                last_published_at=last_result.scalar_one_or_none(),
                published_turns_in_window=int(count_result.scalar_one()),
            )

    async def add_turn(
        self,
        *,
        trigger_message_id: str,
        channel_id: str,
        character_id: str,
        disposition: AgentTurnDisposition,
        decision: AgentTurnDecision | None,
        failure_reason: str | None = None,
    ) -> AgentTurnRecord:
        async with self._session_factory() as session:
            table = cast(Any, AgentTurnORM).__table__
            existing_result = await session.execute(
                select(AgentTurnORM).where(
                    table.c.trigger_message_id == trigger_message_id
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                return _turn_record(existing)
            now = datetime.now(UTC)
            row = AgentTurnORM(
                id=str(ULID()),
                trigger_message_id=trigger_message_id,
                channel_id=channel_id,
                character_id=character_id,
                disposition=disposition.value,
                private_reflection=(
                    decision.private_reflection.model_dump(mode="json")
                    if decision is not None
                    else None
                ),
                proposed_texts=list(decision.texts) if decision is not None else [],
                published_external_message_ids=[],
                failure_reason=failure_reason,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return _turn_record(row)

    async def update_turn(
        self,
        *,
        turn_id: str,
        disposition: AgentTurnDisposition,
        published_external_message_ids: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(AgentTurnORM, turn_id)
            if row is None:
                raise ValueError(f"Agent turn not found: {turn_id}")
            row.disposition = disposition.value
            if published_external_message_ids is not None:
                row.published_external_message_ids = list(
                    published_external_message_ids
                )
            row.failure_reason = failure_reason
            row.updated_at = datetime.now(UTC)
            session.add(row)
            await session.commit()

    async def topic_activity(
        self,
        *,
        guild_id: str,
        channel_id: str,
        character_id: str,
        window_started_at: datetime,
    ) -> AutonomousTopicActivity:
        async with self._session_factory() as session:
            message_table = cast(Any, DiscussionMessageORM).__table__
            latest_result = await session.execute(
                select(DiscussionMessageORM)
                .where(
                    message_table.c.guild_id == guild_id,
                    message_table.c.channel_id == channel_id,
                )
                .order_by(desc(message_table.c.occurred_at), desc(message_table.c.id))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()

            topic_table = cast(Any, AutonomousTopicTurnORM).__table__
            last_result = await session.execute(
                select(func.max(topic_table.c.created_at)).where(
                    topic_table.c.guild_id == guild_id,
                    topic_table.c.channel_id == channel_id,
                    topic_table.c.character_id == character_id,
                )
            )
            count_result = await session.execute(
                select(func.count(topic_table.c.id)).where(
                    topic_table.c.guild_id == guild_id,
                    topic_table.c.channel_id == channel_id,
                    topic_table.c.character_id == character_id,
                    topic_table.c.disposition == AgentTurnDisposition.PUBLISHED.value,
                    topic_table.c.updated_at >= _as_utc(window_started_at),
                )
            )
            return AutonomousTopicActivity(
                latest_message_id=latest.id if latest is not None else None,
                latest_message_at=(
                    _as_utc(latest.occurred_at) if latest is not None else None
                ),
                last_evaluated_at=last_result.scalar_one_or_none(),
                published_topics_in_window=int(count_result.scalar_one()),
            )

    async def add_topic_turn(
        self,
        *,
        guild_id: str,
        channel_id: str,
        character_id: str,
        baseline_message_id: str | None,
        disposition: AgentTurnDisposition,
        decision: AgentTurnDecision | None,
        failure_reason: str | None = None,
    ) -> AutonomousTopicTurnRecord:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            row = AutonomousTopicTurnORM(
                id=str(ULID()),
                guild_id=guild_id,
                channel_id=channel_id,
                character_id=character_id,
                baseline_message_id=baseline_message_id,
                disposition=disposition.value,
                private_reflection=(
                    decision.private_reflection.model_dump(mode="json")
                    if decision is not None
                    else None
                ),
                proposed_texts=list(decision.texts) if decision is not None else [],
                published_external_message_ids=[],
                failure_reason=failure_reason,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return _topic_turn_record(row)

    async def update_topic_turn(
        self,
        *,
        turn_id: str,
        disposition: AgentTurnDisposition,
        published_external_message_ids: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(AutonomousTopicTurnORM, turn_id)
            if row is None:
                raise ValueError(f"Autonomous topic turn not found: {turn_id}")
            row.disposition = disposition.value
            if published_external_message_ids is not None:
                row.published_external_message_ids = list(
                    published_external_message_ids
                )
            row.failure_reason = failure_reason
            row.updated_at = datetime.now(UTC)
            session.add(row)
            await session.commit()

    async def _find_by_external_id(
        self, session: AsyncSession, external_message_id: str
    ) -> DiscussionMessageORM | None:
        table = cast(Any, DiscussionMessageORM).__table__
        result = await session.execute(
            select(DiscussionMessageORM).where(
                table.c.external_message_id == external_message_id
            )
        )
        return result.scalar_one_or_none()


def _observed(row: DiscussionMessageORM, *, is_new: bool) -> ObservedDiscussionMessage:
    return ObservedDiscussionMessage(
        message_id=row.id,
        external_message_id=row.external_message_id,
        guild_id=row.guild_id,
        channel_id=row.channel_id,
        author_external_id=row.author_external_id,
        author_display_name=row.author_display_name,
        author_kind=DiscussionAuthorKind(row.author_kind),
        text=row.message_text,
        mentioned_self=row.mentioned_self,
        occurred_at=_as_utc(row.occurred_at),
        recovered=row.recovered,
        is_new=is_new,
    )


def _history_item(row: DiscussionMessageORM) -> DiscussionHistoryItem:
    return DiscussionHistoryItem(
        message_id=row.id,
        external_message_id=row.external_message_id,
        author_external_id=row.author_external_id,
        author_display_name=row.author_display_name,
        author_kind=DiscussionAuthorKind(row.author_kind),
        text=row.message_text,
        occurred_at=_as_utc(row.occurred_at),
    )


def _turn_record(row: AgentTurnORM) -> AgentTurnRecord:
    return AgentTurnRecord(
        turn_id=row.id,
        trigger_message_id=row.trigger_message_id,
        character_id=row.character_id,
        disposition=AgentTurnDisposition(row.disposition),
        private_reflection=(
            PrivateReflection.model_validate(row.private_reflection)
            if row.private_reflection is not None
            else None
        ),
        proposed_texts=list(row.proposed_texts),
        published_external_message_ids=list(row.published_external_message_ids),
        failure_reason=row.failure_reason,
        created_at=_as_utc(row.created_at or datetime.now(UTC)),
    )


def _topic_turn_record(row: AutonomousTopicTurnORM) -> AutonomousTopicTurnRecord:
    return AutonomousTopicTurnRecord(
        turn_id=row.id,
        guild_id=row.guild_id,
        channel_id=row.channel_id,
        character_id=row.character_id,
        baseline_message_id=row.baseline_message_id,
        disposition=AgentTurnDisposition(row.disposition),
        private_reflection=(
            PrivateReflection.model_validate(row.private_reflection)
            if row.private_reflection is not None
            else None
        ),
        proposed_texts=list(row.proposed_texts),
        published_external_message_ids=list(row.published_external_message_ids),
        failure_reason=row.failure_reason,
        created_at=_as_utc(row.created_at or datetime.now(UTC)),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
