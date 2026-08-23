"""Canonical user identity lookup boundary."""

from abc import ABC, abstractmethod

from flow_res import Result

from app.domain.aggregates.user import User, UserChannelIdentity
from app.domain.repositories.interfaces import RepositoryError


class IUserIdentityQuery(ABC):
    """Resolve a canonical user from an external channel identity."""

    @abstractmethod
    async def find_user(
        self, identity: UserChannelIdentity
    ) -> Result[User | None, RepositoryError]:
        """Return the owning user, or ``None`` when it is not registered."""

        raise NotImplementedError
