"""Retrieve memory context use case."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Ok, Result, is_err
from injector import inject

from app.contracts.messages.memory_context import MemoryContextPack
from app.contracts.ports.memory_service import IMemoryService
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class RetrieveMemoryContextQuery(Request[Result[MemoryContextPack, UseCaseError]]):
    """Query to resolve prompt-ready memory context."""

    user_id: str


class RetrieveMemoryContextHandler(
    RequestHandler[RetrieveMemoryContextQuery, Result[MemoryContextPack, UseCaseError]]
):
    """Handle RetrieveMemoryContextQuery."""

    @inject
    def __init__(self, memory_service: IMemoryService) -> None:
        self._memory_service = memory_service

    async def handle(
        self, request: RetrieveMemoryContextQuery
    ) -> Result[MemoryContextPack, UseCaseError]:
        """Resolve memory context through the memory port."""
        memory_result = await self._memory_service.build_context(request.user_id)
        if is_err(memory_result):
            return memory_result.map_err(
                lambda _: UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message="Failed to retrieve memory context",
                )
            )
        return Ok(memory_result.value)
