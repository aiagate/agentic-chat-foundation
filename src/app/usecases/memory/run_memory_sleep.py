"""Run memory sleep scheduled job use case."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_store import IMemoryStore
from app.domain.repositories import IUnitOfWork
from app.usecases.result import ErrorType, UseCaseError

logger = logging.getLogger(__name__)


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
        now = datetime.now(UTC)
        run_key = _memory_sleep_run_key(now)

        async with self._uow:
            run_repository = self._uow.GetMemoryConsolidationRunRepository()
            claim_result = await run_repository.claim_run(
                run_key=run_key,
                job_name="memory_sleep",
                target_date=now.date(),
                started_at=now,
            )
            if is_err(claim_result):
                error = claim_result.error
                logger.error("Failed to claim memory sleep run")
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=f"Failed to claim memory sleep run: {error}",
                    )
                )

            claim = claim_result.value
            if not claim.acquired:
                return Ok(RunMemorySleepResult(consolidated_count=0))

            commit_result = await self._uow.commit()
            if is_err(commit_result):
                logger.error("Failed to persist memory sleep run state")
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to persist memory sleep run state",
                    )
                )

        async with self._uow:
            try:
                raw_chat_log_query = self._uow.GetRawChatLogQuery()
                run_repository = self._uow.GetMemoryConsolidationRunRepository()
                consolidated_count = await (
                    self._memory_consolidation_service.run_memory_sleep(
                        self._memory_store,
                        run_key=run_key,
                        started_at=now,
                        raw_chat_log_query=raw_chat_log_query,
                        run_repository=run_repository,
                    )
                )
                result: Result[RunMemorySleepResult, UseCaseError] = Ok(
                    RunMemorySleepResult(consolidated_count=consolidated_count)
                )
            except Exception as exc:
                logger.exception("Failed to run memory sleep job")
                result = Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=f"Failed to run memory sleep job: {exc}",
                    )
                )

            commit_result = await self._uow.commit()
            if is_err(commit_result):
                logger.error("Failed to persist memory sleep run state")
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message="Failed to persist memory sleep run state",
                    )
                )

            return result


def _memory_sleep_run_key(reference_time: datetime) -> str:
    """Build the deterministic run key for a sleep execution."""

    return f"memory-sleep:{reference_time.date().isoformat()}"
