"""Run memory sleep scheduled job use case."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from flow_med import Request, RequestHandler
from flow_res import Err, Ok, Result, is_err
from injector import inject

from app.contracts.messages.use_case_error import ErrorType, UseCaseError
from app.contracts.ports.memory_consolidation import IMemoryConsolidationService
from app.contracts.ports.memory_store import IMemoryStore
from app.contracts.ports.unit_of_work import IUnitOfWork
from app.domain.queries.memory_sleep_query import IMemorySleepQuery

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunMemorySleepResult:
    """Summary of one scheduled memory sleep run."""

    consolidated_count: int


@dataclass(frozen=True)
class RunMemorySleepCommand(Request[Result[RunMemorySleepResult, UseCaseError]]):
    """Command to run the scheduled memory sleep job."""

    reference_time: datetime | None = None


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
        memory_sleep_query_service: IMemorySleepQuery,
    ) -> None:
        self._memory_store = memory_store
        self._uow = uow
        self._memory_consolidation_service = memory_consolidation_service
        self._memory_sleep_query_service = memory_sleep_query_service

    async def handle(
        self,
        request: RunMemorySleepCommand,
    ) -> Result[RunMemorySleepResult, UseCaseError]:
        """Run the scheduled sleep job through the query and consolidation services."""

        async with self._uow:
            try:
                reference_time = request.reference_time or datetime.now(UTC)
                if reference_time.tzinfo is None:
                    reference_time = reference_time.replace(tzinfo=UTC)
                else:
                    reference_time = reference_time.astimezone(UTC)
                logger.info(
                    "Starting memory sleep run for reference_time=%s",
                    reference_time.isoformat(),
                )
                raw_chat_log_query = self._uow.GetRawChatLogQuery()
                targets = await self._memory_sleep_query_service.list_pending_targets(
                    raw_chat_log_query,
                    reference_time=reference_time,
                )
                logger.info(
                    "Memory sleep targets resolved: %s",
                    len(targets),
                )
                consolidated_count = 0
                for target in targets:
                    consolidated_count += await (
                        self._memory_consolidation_service.consolidate_chat_logs(
                            self._memory_store,
                            user_id=target.user_id,
                            day=target.day,
                            raw_logs=target.raw_logs,
                            reference_time=reference_time,
                        )
                    )
                    source_repository = (
                        self._uow.GetMemoryConsolidatedChatSourceRepository()
                    )
                    mark_result = await source_repository.mark_consolidated(
                        [raw_log.id for raw_log in target.raw_logs],
                        consolidated_at=reference_time,
                    )
                    if is_err(mark_result):
                        raise RuntimeError(mark_result.error.message)
                    commit_result = await self._uow.commit()
                    if is_err(commit_result):
                        raise RuntimeError(commit_result.error.message)
                logger.info(
                    "Memory sleep run completed: consolidated_count=%s",
                    consolidated_count,
                )
                return Ok(RunMemorySleepResult(consolidated_count=consolidated_count))
            except Exception as exc:
                logger.error(
                    "Failed to run memory sleep job: %s",
                    exc,
                    exc_info=True,
                )
                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=f"Failed to run memory sleep job: {exc}",
                    )
                )
