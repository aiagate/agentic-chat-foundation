"""Repair memory index use case."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.ports.memory_index_maintenance import IMemoryIndexMaintenance
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class RepairMemoryIndexResult:
    """Summary of a memory index repair."""

    repaired_count: int


@dataclass(frozen=True)
class RepairMemoryIndexCommand(Request[Result[RepairMemoryIndexResult, UseCaseError]]):
    """Command to repair stale memory index rows."""

    user_id: str | None = None


class RepairMemoryIndexHandler(
    RequestHandler[
        RepairMemoryIndexCommand,
        Result[RepairMemoryIndexResult, UseCaseError],
    ]
):
    """Handle RepairMemoryIndexCommand."""

    @inject
    def __init__(
        self,
        memory_index_maintenance: IMemoryIndexMaintenance,
    ) -> None:
        self._memory_index_maintenance = memory_index_maintenance

    async def handle(
        self, request: RepairMemoryIndexCommand
    ) -> Result[RepairMemoryIndexResult, UseCaseError]:
        """Repair the persistent memory index through the port."""
        index_result = await self._memory_index_maintenance.repair_memory_index(
            user_id=request.user_id,
        )
        if is_err(index_result):
            return Err(
                UseCaseError(
                    type=ErrorType.UNEXPECTED,
                    message=f"Failed to repair memory index: {index_result.error}",
                )
            )
        return Ok(RepairMemoryIndexResult(repaired_count=index_result.value))
