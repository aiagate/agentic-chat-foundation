"""Errors for TeamMembership aggregate transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TeamMembershipTransitionErrorType(Enum):
    """Types of TeamMembership transition failures."""

    INVALID_STATUS_TRANSITION = auto()


@dataclass(frozen=True)
class TeamMembershipTransitionError(Exception):
    """Domain error returned when membership transition is not allowed."""

    type: TeamMembershipTransitionErrorType
    message: str
