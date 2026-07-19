"""SQLAlchemy user identity query."""

from typing import Any, cast

from flow_res import Err, Ok, Result
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.ports.user_identity_query import IUserIdentityQuery
from app.domain.aggregates.user import User, UserChannelIdentity
from app.domain.repositories.interfaces import RepositoryError, RepositoryErrorType
from app.infrastructure.orm_models.user_orm import UserChannelIdentityORM


class SQLAlchemyUserIdentityQuery(IUserIdentityQuery):
    """Resolve User aggregates using a short-lived database session."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_user(
        self, identity: UserChannelIdentity
    ) -> Result[User | None, RepositoryError]:
        try:
            async with self._session_factory() as session:
                table = cast(Any, UserChannelIdentityORM).__table__
                owner_result = await session.execute(
                    select(table.c.user_id).where(
                        table.c.channel == identity.channel,
                        table.c.external_participant_id
                        == identity.external_participant_id,
                    )
                )
                user_id = owner_result.scalar_one_or_none()
                if user_id is None:
                    return Ok(None)
                identities_result = await session.execute(
                    select(UserChannelIdentityORM).where(table.c.user_id == user_id)
                )
                identities = tuple(
                    UserChannelIdentity(
                        channel=item.channel,
                        external_participant_id=item.external_participant_id,
                    )
                    for item in identities_result.scalars().all()
                )
                return Ok(User(id=user_id, identities=identities))
        except (SQLAlchemyError, ValueError) as exc:
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )
