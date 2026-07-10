"""Errors returned across application use case boundaries."""

from dataclasses import dataclass
from enum import Enum, auto


class ErrorType(Enum):
    """Stable categories for application errors."""

    NOT_FOUND = auto()
    VALIDATION_ERROR = auto()
    UNEXPECTED = auto()
    CONCURRENCY_CONFLICT = auto()


@dataclass
class UseCaseError(Exception):
    """Error returned by an application use case."""

    type: ErrorType
    message: str

    def __str__(self) -> str:
        return self.message
