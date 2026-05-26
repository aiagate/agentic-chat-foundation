"""Run memory sleep scheduled job use case."""

from __future__ import annotations

from dataclasses import dataclass

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result
from injector import inject

from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.repositories import IUnitOfWork
from app.usecases.result import ErrorType, UseCaseError


@dataclass(frozen=True)
class RunMemorySleepResult:
    """Summary of one scheduled memory sleep run."""

    consolidated_count: int


@dataclass(frozen=True)
class RunMemorySleepCommand(Request[Result[RunMemorySleepResult, UseCaseError]]):
    """Command to run the scheduled memory sleep job."""


class RunMemorySleepHandler(
    RequestHandler[
        RunMemorySleepCommand,
        Result[RunMemorySleepResult, UseCaseError],
    ]
):
    """Handle RunMemorySleepCommand."""

    @inject
    def __init__(
        self,
        memory_store: IMemoryStore,
        uow: IUnitOfWork,
        memory_consolidation_service: IMemoryConsolidationService,
    ) -> None:
        self._memory_store = memory_store
        self._uow = uow
        self._memory_consolidation_service = memory_consolidation_service

    async def handle(
        self,
        request: RunMemorySleepCommand,
    ) -> Result[RunMemorySleepResult, UseCaseError]:
        """Run the scheduled sleep job through the consolidation service."""

        del request
        async with self._uow:
            try:
                raw_chat_log_query = self._uow.GetRawChatLogQuery()
                consolidated_count = (
                    await self._memory_consolidation_service.run_memory_sleep(
                        self._memory_store,
                        raw_chat_log_query=raw_chat_log_query,
                    )
                )
                return Ok(RunMemorySleepResult(consolidated_count=consolidated_count))
            except Exception as exc:
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=f"Failed to run memory sleep job: {exc}",
                    )
                )
