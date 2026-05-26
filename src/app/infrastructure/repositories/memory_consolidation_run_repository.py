"""SQLAlchemy repository for memory consolidation run records."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from flow_res import Err, Ok, Result
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories import (
    IMemoryConsolidationRunRepository,
    MemoryConsolidationRunClaim,
    MemoryConsolidationRunRecord,
    MemoryConsolidationRunStatus,
    RepositoryError,
    RepositoryErrorType,
)
from app.infrastructure.orm_models.memory_consolidation_run_orm import (
    MemoryConsolidationRunORM,
)

logger = logging.getLogger(__name__)


class SQLAlchemyMemoryConsolidationRunRepository(IMemoryConsolidationRunRepository):
    """Persist and update memory consolidation run state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_run_key(
        self,
        run_key: str,
    ) -> Result[MemoryConsolidationRunRecord | None, RepositoryError]:
        """Get a run record by its unique run key."""

        try:
            record = await self._load_run(run_key)
            if record is None:
                return Ok(None)
            return Ok(self._to_record(record))
        except SQLAlchemyError as exc:
            logger.exception("Database error occurred in run lookup")
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )

    async def claim_run(
        self,
        *,
        run_key: str,
        job_name: str,
        target_date: date | None,
        started_at: datetime,
    ) -> Result[MemoryConsolidationRunClaim, RepositoryError]:
        """Claim a pending run and transition it to processing."""

        try:
            existing = await self._load_run(run_key)
            if existing is not None:
                if existing.status != "pending":
                    return Ok(
                        MemoryConsolidationRunClaim(
                            record=self._to_record(existing),
                            acquired=False,
                        )
                    )

                existing.job_name = job_name
                existing.target_date = target_date
                existing.status = "processing"
                existing.started_at = started_at
                existing.finished_at = None
                existing.result_json = _build_claim_result_json(
                    run_key=run_key,
                    job_name=job_name,
                    target_date=target_date,
                    started_at=started_at,
                )
                await self._session.flush()
                return Ok(
                    MemoryConsolidationRunClaim(
                        record=self._to_record(existing),
                        acquired=True,
                    )
                )

            run = MemoryConsolidationRunORM(
                run_key=run_key,
                job_name=job_name,
                target_date=target_date,
                status="processing",
                started_at=started_at,
                finished_at=None,
                result_json=_build_claim_result_json(
                    run_key=run_key,
                    job_name=job_name,
                    target_date=target_date,
                    started_at=started_at,
                ),
            )
            self._session.add(run)
            await self._session.flush()
            return Ok(
                MemoryConsolidationRunClaim(
                    record=self._to_record(run),
                    acquired=True,
                )
            )
        except IntegrityError:
            await self._session.rollback()
            existing = await self._load_run(run_key)
            if existing is None:
                return Err(
                    RepositoryError(
                        type=RepositoryErrorType.UNEXPECTED,
                        message="Failed to claim memory consolidation run",
                    )
                )
            if existing.status != "pending":
                return Ok(
                    MemoryConsolidationRunClaim(
                        record=self._to_record(existing),
                        acquired=False,
                    )
                )
            try:
                existing.job_name = job_name
                existing.target_date = target_date
                existing.status = "processing"
                existing.started_at = started_at
                existing.finished_at = None
                existing.result_json = _build_claim_result_json(
                    run_key=run_key,
                    job_name=job_name,
                    target_date=target_date,
                    started_at=started_at,
                )
                await self._session.flush()
                return Ok(
                    MemoryConsolidationRunClaim(
                        record=self._to_record(existing),
                        acquired=True,
                    )
                )
            except SQLAlchemyError as exc:
                logger.exception("Database error occurred while claiming run")
                return Err(
                    RepositoryError(
                        type=RepositoryErrorType.UNEXPECTED,
                        message=str(exc),
                    )
                )
        except SQLAlchemyError as exc:
            logger.exception("Database error occurred while claiming run")
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )

    async def set_run_result(
        self,
        *,
        run_key: str,
        status: MemoryConsolidationRunStatus,
        finished_at: datetime,
        result_json: dict[str, Any],
    ) -> Result[MemoryConsolidationRunRecord, RepositoryError]:
        """Persist a terminal run result."""

        try:
            record = await self._load_run(run_key)
            if record is None:
                return Err(
                    RepositoryError(
                        type=RepositoryErrorType.NOT_FOUND,
                        message=f"Memory consolidation run {run_key} not found",
                    )
                )
            record.status = status
            record.finished_at = finished_at
            record.result_json = dict(result_json)
            await self._session.flush()
            return Ok(self._to_record(record))
        except SQLAlchemyError as exc:
            logger.exception("Database error occurred while updating run result")
            return Err(
                RepositoryError(
                    type=RepositoryErrorType.UNEXPECTED,
                    message=str(exc),
                )
            )

    async def _load_run(
        self,
        run_key: str,
    ) -> MemoryConsolidationRunORM | None:
        table = cast(Any, MemoryConsolidationRunORM).__table__
        statement = select(MemoryConsolidationRunORM).where(table.c.run_key == run_key)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    def _to_record(
        self,
        run: MemoryConsolidationRunORM,
    ) -> MemoryConsolidationRunRecord:
        return MemoryConsolidationRunRecord(
            id=run.id,
            run_key=run.run_key,
            job_name=run.job_name,
            target_date=run.target_date,
            status=cast(MemoryConsolidationRunStatus, run.status),
            started_at=_as_utc(run.started_at),
            finished_at=_as_utc(run.finished_at),
            result_json=dict(run.result_json),
        )


def _build_claim_result_json(
    *,
    run_key: str,
    job_name: str,
    target_date: date | None,
    started_at: datetime,
) -> dict[str, Any]:
    """Build deterministic metadata for a claimed run."""

    result_json: dict[str, Any] = {
        "run_key": run_key,
        "job_name": job_name,
        "started_at": started_at.isoformat(),
    }
    if target_date is not None:
        result_json["target_date"] = target_date.isoformat()
    return result_json


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize timestamps loaded from SQLite to UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
