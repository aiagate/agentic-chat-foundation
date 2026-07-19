"""SQLAlchemy relationship aggregate repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from flow_res import Err, Ok, Result
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.contracts.messages.relationship import (
    PersistedRelationshipSignal,
    RelationshipSignalStatus,
)
from app.domain.aggregates.character_relationship import (
    CharacterRelationship,
)
from app.domain.repositories import (
    ICharacterRelationshipRepository,
    RepositoryError,
    RepositoryErrorType,
)
from app.domain.services.relationship_recalculation import (
    RelationshipEventInput,
    recalculate_affection,
)
from app.infrastructure.orm_models.relationship_orm import (
    CharacterRelationshipORM,
    RelationshipSignalEventORM,
    RelationshipSignalSourceORM,
)


class CharacterRelationshipRepository(ICharacterRelationshipRepository):
    """Persist signals and rebuild the current affection snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_provisional(
        self,
        signal: PersistedRelationshipSignal,
    ) -> Result[CharacterRelationship, RepositoryError]:
        try:
            await self._ensure_relationship(signal.character_id, signal.user_id)
            await self._supersede_overlapping(
                character_id=signal.character_id,
                user_id=signal.user_id,
                chat_ids=signal.source_chat_ids,
                only_status=RelationshipSignalStatus.PROVISIONAL,
                except_signal_ids={signal.id},
            )
            await self._upsert_signal(signal)
            return Ok(await self._recalculate(signal.character_id, signal.user_id))
        except (IntegrityError, StaleDataError) as exc:
            return Err(RepositoryError(RepositoryErrorType.VERSION_CONFLICT, str(exc)))
        except SQLAlchemyError as exc:
            return Err(RepositoryError(RepositoryErrorType.UNEXPECTED, str(exc)))

    async def reconcile_confirmed(
        self,
        *,
        character_id: str,
        user_id: str,
        evaluated_chat_ids: list[str],
        signals: list[PersistedRelationshipSignal],
    ) -> Result[CharacterRelationship, RepositoryError]:
        try:
            await self._ensure_relationship(character_id, user_id)
            unique_chat_ids = list(dict.fromkeys(evaluated_chat_ids))
            if unique_chat_ids:
                await self._supersede_overlapping(
                    character_id=character_id,
                    user_id=user_id,
                    chat_ids=unique_chat_ids,
                    only_status=None,
                    except_signal_ids={signal.id for signal in signals},
                )
            for signal in signals:
                await self._upsert_signal(signal)
            return Ok(await self._recalculate(character_id, user_id))
        except (IntegrityError, StaleDataError) as exc:
            return Err(RepositoryError(RepositoryErrorType.VERSION_CONFLICT, str(exc)))
        except SQLAlchemyError as exc:
            return Err(RepositoryError(RepositoryErrorType.UNEXPECTED, str(exc)))

    async def _supersede_overlapping(
        self,
        *,
        character_id: str,
        user_id: str,
        chat_ids: list[str],
        only_status: RelationshipSignalStatus | None,
        except_signal_ids: set[str],
    ) -> None:
        if not chat_ids:
            return
        event_table = cast(Any, RelationshipSignalEventORM).__table__
        source_table = cast(Any, RelationshipSignalSourceORM).__table__
        statement = (
            select(RelationshipSignalEventORM)
            .join(source_table, source_table.c.signal_id == event_table.c.id)
            .where(
                event_table.c.character_id == character_id,
                event_table.c.user_id == user_id,
                event_table.c.status != RelationshipSignalStatus.SUPERSEDED.value,
                source_table.c.chat_id.in_(list(dict.fromkeys(chat_ids))),
            )
        )
        if only_status is not None:
            statement = statement.where(event_table.c.status == only_status.value)
        if except_signal_ids:
            statement = statement.where(
                event_table.c.id.not_in(sorted(except_signal_ids))
            )
        overlapping = (await self._session.execute(statement)).scalars()
        events_by_id = {event.id: event for event in overlapping.all()}
        for event in events_by_id.values():
            event.status = RelationshipSignalStatus.SUPERSEDED.value

    async def _ensure_relationship(self, character_id: str, user_id: str) -> None:
        row = await self._load_relationship(character_id, user_id)
        if row is None:
            self._session.add(
                CharacterRelationshipORM(
                    character_id=character_id,
                    user_id=user_id,
                    affection=0,
                    version=1,
                )
            )
            await self._session.flush()

    async def _load_relationship(
        self, character_id: str, user_id: str
    ) -> CharacterRelationshipORM | None:
        table = cast(Any, CharacterRelationshipORM).__table__
        return (
            await self._session.execute(
                select(CharacterRelationshipORM).where(
                    table.c.character_id == character_id,
                    table.c.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def _upsert_signal(self, signal: PersistedRelationshipSignal) -> None:
        event = await self._session.get(RelationshipSignalEventORM, signal.id)
        if event is None:
            event = RelationshipSignalEventORM(
                id=signal.id,
                character_id=signal.character_id,
                user_id=signal.user_id,
                kind=signal.kind.value,
                status=signal.status.value,
                confidence=signal.confidence,
                proposed_delta=signal.proposed_delta,
                applied_delta=0,
                reason=signal.reason,
                observed_at=_as_utc(signal.observed_at),
            )
            self._session.add(event)
            await self._session.flush()
        else:
            event.kind = signal.kind.value
            event.status = signal.status.value
            event.confidence = signal.confidence
            event.proposed_delta = signal.proposed_delta
            event.reason = signal.reason
            event.observed_at = _as_utc(signal.observed_at)
        source_table = cast(Any, RelationshipSignalSourceORM).__table__
        existing_sources = set(
            (
                await self._session.execute(
                    select(source_table.c.chat_id).where(
                        source_table.c.signal_id == signal.id
                    )
                )
            ).scalars()
        )
        for chat_id in signal.source_chat_ids:
            if chat_id not in existing_sources:
                self._session.add(
                    RelationshipSignalSourceORM(signal_id=signal.id, chat_id=chat_id)
                )
        await self._session.flush()

    async def _recalculate(
        self, character_id: str, user_id: str
    ) -> CharacterRelationship:
        relationship = await self._load_relationship(character_id, user_id)
        if relationship is None:
            raise RuntimeError("relationship disappeared during recalculation")
        event_table = cast(Any, RelationshipSignalEventORM).__table__
        events = list(
            (
                await self._session.execute(
                    select(RelationshipSignalEventORM)
                    .where(
                        event_table.c.character_id == character_id,
                        event_table.c.user_id == user_id,
                        event_table.c.status
                        != RelationshipSignalStatus.SUPERSEDED.value,
                    )
                    .order_by(
                        event_table.c.observed_at,
                        event_table.c.id,
                    )
                )
            ).scalars()
        )
        recalculation = recalculate_affection(
            [
                RelationshipEventInput(
                    id=event.id,
                    proposed_delta=event.proposed_delta,
                    observed_at=event.observed_at,
                )
                for event in events
            ]
        )
        applied_by_id = {
            event.id: event.applied_delta for event in recalculation.applied_events
        }
        for event in events:
            event.applied_delta = applied_by_id[event.id]
        affection = recalculation.affection
        expected_version = relationship.version
        created_at = relationship.created_at
        next_version = expected_version + 1
        updated_at = datetime.now(UTC)
        relationship_table = cast(Any, CharacterRelationshipORM).__table__
        update_result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(CharacterRelationshipORM)
                .where(
                    relationship_table.c.character_id == character_id,
                    relationship_table.c.user_id == user_id,
                    relationship_table.c.version == expected_version,
                )
                .values(
                    affection=affection,
                    version=next_version,
                    updated_at=updated_at,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if update_result.rowcount != 1:
            raise StaleDataError(
                f"relationship version conflict: {character_id}/{user_id} "
                f"expected version {expected_version}"
            )
        self._session.expire(relationship)
        await self._session.flush()
        return CharacterRelationship(
            character_id=character_id,
            user_id=user_id,
            affection=affection,
            version=next_version,
            created_at=created_at,
            updated_at=updated_at,
        )


def _as_utc(value: datetime) -> datetime:
    return (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
