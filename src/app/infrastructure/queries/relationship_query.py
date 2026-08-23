"""SQLAlchemy relationship state query."""

from __future__ import annotations

from typing import Any, cast

from flow_res import Err, Ok, Result
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.messages.relationship import RelationshipStateView
from app.contracts.ports.relationship import IRelationshipQuery, RelationshipQueryError
from app.domain.aggregates.character_relationship import resolve_relationship_stage
from app.infrastructure.orm_models.relationship_orm import CharacterRelationshipORM


class SQLAlchemyRelationshipQuery(IRelationshipQuery):
    """Read current affection without leaking ORM details."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(
        self,
        *,
        character_id: str,
        user_id: str,
    ) -> Result[RelationshipStateView, RelationshipQueryError]:
        try:
            table = cast(Any, CharacterRelationshipORM).__table__
            async with self._session_factory() as session:
                row = (
                    await session.execute(
                        select(CharacterRelationshipORM).where(
                            table.c.character_id == character_id,
                            table.c.user_id == user_id,
                        )
                    )
                ).scalar_one_or_none()
            affection = row.affection if row is not None else 0
            version = row.version if row is not None else 1
            return Ok(
                RelationshipStateView(
                    character_id=character_id,
                    user_id=user_id,
                    affection=affection,
                    stage_id=resolve_relationship_stage(affection),
                    version=version,
                )
            )
        except SQLAlchemyError as exc:
            return Err(RelationshipQueryError(str(exc)))
