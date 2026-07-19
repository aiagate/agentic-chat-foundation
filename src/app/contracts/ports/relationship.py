"""Application boundaries for relationship reads and signal evaluation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from flow_res import Result

from app.contracts.messages.conversation import AcceptedMessage
from app.contracts.messages.relationship import (
    RelationshipSignalCandidate,
    RelationshipSignalEvaluationRequest,
    RelationshipStateView,
)


@dataclass(frozen=True, slots=True)
class RelationshipQueryError(Exception):
    """Failure to read a relationship state."""

    message: str


class IRelationshipQuery(ABC):
    """Read one character-user relationship state."""

    @abstractmethod
    async def get(
        self,
        *,
        character_id: str,
        user_id: str,
    ) -> Result[RelationshipStateView, RelationshipQueryError]:
        """Return persisted state or the initial zero state."""

        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RelationshipSignalEvaluationError(Exception):
    """Failure to classify a relationship signal."""

    message: str


class IRelationshipSignalEvaluator(ABC):
    """Classify relationship evidence behind an external AI boundary."""

    @abstractmethod
    async def evaluate(
        self,
        request: RelationshipSignalEvaluationRequest,
    ) -> Result[RelationshipSignalCandidate, RelationshipSignalEvaluationError]:
        """Return one validated semantic signal candidate."""

        raise NotImplementedError


class IRelationshipInteractionProcessor(ABC):
    """Evaluate and persist one immediate relationship interaction."""

    @abstractmethod
    async def process(self, message: AcceptedMessage) -> None:
        """Persist a provisional signal or return without changing state."""

        raise NotImplementedError
