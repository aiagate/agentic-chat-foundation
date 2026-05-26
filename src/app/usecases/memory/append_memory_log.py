"""Append memory log use case."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Ok, Result, is_err
from injector import inject

from app.contracts.ports.memory_service import IMemoryService
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class AppendMemoryLogCommand(Request[Result[None, UseCaseError]]):
    """Command to append a raw memory log entry."""

    user_id: str
    role: str
    content: str
    metadata: dict[str, str]


class AppendMemoryLogHandler(
    RequestHandler[AppendMemoryLogCommand, Result[None, UseCaseError]]
):
    """Handle AppendMemoryLogCommand."""

    @inject
    def __init__(self, memory_service: IMemoryService) -> None:
        self._memory_service = memory_service

    async def handle(
        self, request: AppendMemoryLogCommand
    ) -> Result[None, UseCaseError]:
        """Persist raw memory through the memory port."""
        memory_result = await self._memory_service.add_log(
            request.user_id,
            request.role,
            request.content,
            request.metadata,
        )
        if is_err(memory_result):
            return memory_result.map_err(
                lambda _: UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Failed to persist memory context",
                )
            )
        return Ok(None)
