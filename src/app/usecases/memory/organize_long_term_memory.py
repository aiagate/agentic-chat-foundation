"""Periodic long-term memory organization use case."""

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
from app.domain.queries.long_term_memory_query import ILongTermMemoryQuery

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrganizeLongTermMemoryResult:
    """Summary of one periodic long-term memory organization run."""

    consolidated_count: int


@dataclass(frozen=True)
class OrganizeLongTermMemoryCommand(
    Request[Result[OrganizeLongTermMemoryResult, UseCaseError]]
):
    """Organize pending conversation history into long-term memory."""

    reference_time: datetime | None = None


class OrganizeLongTermMemoryHandler(
    RequestHandler[
        OrganizeLongTermMemoryCommand,
        Result[OrganizeLongTermMemoryResult, UseCaseError],
    ]
):
    """Handle OrganizeLongTermMemoryCommand."""

    @inject
    def __init__(
        self,
        memory_store: IMemoryStore,
        uow: IUnitOfWork,
        memory_consolidation_service: IMemoryConsolidationService,
        long_term_memory_query: ILongTermMemoryQuery,
    ) -> None:
        self._memory_store = memory_store
        self._uow = uow
        self._memory_consolidation_service = memory_consolidation_service
        self._long_term_memory_query = long_term_memory_query

    async def handle(
        self,
        request: OrganizeLongTermMemoryCommand,
    ) -> Result[OrganizeLongTermMemoryResult, UseCaseError]:
        """Organize each pending user/day batch and mark it complete."""

        async with self._uow:
            try:
                reference_time = request.reference_time or datetime.now(UTC)
                if reference_time.tzinfo is None:
                    reference_time = reference_time.replace(tzinfo=UTC)
                else:
                    reference_time = reference_time.astimezone(UTC)
                logger.info(
                    "Starting long-term memory organization for reference_time=%s",
                    reference_time.isoformat(),
                )
                raw_chat_log_query = self._uow.GetRawChatLogQuery()
                targets = await self._long_term_memory_query.list_pending_targets(
                    raw_chat_log_query,
                    reference_time=reference_time,
                )
                logger.info(
                    "Long-term memory targets resolved: %s",
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
                    "Long-term memory organization completed: consolidated_count=%s",
                    consolidated_count,
                )
                return Ok(
                    OrganizeLongTermMemoryResult(
                        consolidated_count=consolidated_count
                    )
                )
            except Exception as exc:
                logger.error(
                    "Failed to organize long-term memory: %s",
                    exc,
                    exc_info=True,
                )

                return Err(
                    UseCaseError(
                        type=ErrorType.UNEXPECTED,
                        message=f"Failed to organize long-term memory: {exc}",
                    )
                )
