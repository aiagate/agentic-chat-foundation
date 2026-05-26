"""Rebuild memory index use case."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.ports.memory_index import IMemoryIndex
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class RebuildMemoryIndexResult:
    """Summary of a memory index rebuild."""

    indexed_count: int


@dataclass(frozen=True)
class RebuildMemoryIndexCommand(
    Request[Result[RebuildMemoryIndexResult, UseCaseError]]
):
    """Command to rebuild the persistent memory index."""

    user_id: str | None = None


class RebuildMemoryIndexHandler(
    RequestHandler[
        RebuildMemoryIndexCommand,
        Result[RebuildMemoryIndexResult, UseCaseError],
    ]
):
    """Handle RebuildMemoryIndexCommand."""

    @inject
    def __init__(self, memory_index: IMemoryIndex) -> None:
        self._memory_index = memory_index

    async def handle(
        self, request: RebuildMemoryIndexCommand
    ) -> Result[RebuildMemoryIndexResult, UseCaseError]:
        """Rebuild the persistent memory index through the port."""
        index_result = self._memory_index.rebuild_memory_index(
            user_id=request.user_id,
        )
        if is_err(index_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=f"Failed to rebuild memory index: {index_result.error}",
                )
            )
        return Ok(RebuildMemoryIndexResult(indexed_count=index_result.value))
