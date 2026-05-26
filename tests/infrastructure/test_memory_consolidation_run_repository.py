"""Tests for the memory consolidation run repository."""

from datetime import UTC, date, datetime

import pytest
from flow_res import is_ok

from app.domain.repositories import IUnitOfWork
from app.domain.repositories.interfaces import MemoryConsolidationRunStatus


@pytest.mark.anyio
async def test_memory_consolidation_run_repository_claims_and_finalizes(
    uow: IUnitOfWork,
) -> None:
    """Test the claim and terminal-state flow for a run record."""

    started_at = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        claim_result = await repo.claim_run(
            run_key="memory-sleep:2026-05-19",
            job_name="memory_sleep",
            target_date=date(2026, 5, 19),
            started_at=started_at,
        )
        assert is_ok(claim_result)
        claim = claim_result.value
        assert claim.acquired
        assert claim.record.status == "processing"
        assert claim.record.started_at == started_at
        assert claim.record.finished_at is None
        assert claim.record.result_json["run_key"] == "memory-sleep:2026-05-19"
        assert claim.record.result_json["job_name"] == "memory_sleep"
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        record_result = await repo.get_by_run_key("memory-sleep:2026-05-19")
        assert is_ok(record_result)
        record = record_result.value
        assert record is not None
        assert record.status == "processing"
        assert record.started_at == started_at

        finished_at = datetime(2026, 5, 19, 12, 30, tzinfo=UTC)
        finalize_result = await repo.set_run_result(
            run_key="memory-sleep:2026-05-19",
            status="complete",
            finished_at=finished_at,
            result_json={
                "job_name": "memory_sleep",
                "run_key": "memory-sleep:2026-05-19",
                "started_at": started_at.isoformat(),
            },
        )
        assert is_ok(finalize_result)
        assert finalize_result.value.status == "complete"
        assert finalize_result.value.finished_at == finished_at
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        final_result = await repo.get_by_run_key("memory-sleep:2026-05-19")
        assert is_ok(final_result)
        final_record = final_result.value
        assert final_record is not None
        assert final_record.status == "complete"
        assert final_record.finished_at == datetime(2026, 5, 19, 12, 30, tzinfo=UTC)
        assert final_record.result_json["run_key"] == "memory-sleep:2026-05-19"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    ["complete", "failed", "skipped"],
)
async def test_memory_consolidation_run_repository_persists_terminal_states(
    uow: IUnitOfWork,
    status: MemoryConsolidationRunStatus,
) -> None:
    """Test that terminal run statuses are stored without coercion."""

    started_at = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    finished_at = datetime(2026, 5, 20, 12, 5, tzinfo=UTC)

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        claim_result = await repo.claim_run(
            run_key="memory-sleep:2026-05-20",
            job_name="memory_sleep",
            target_date=date(2026, 5, 20),
            started_at=started_at,
        )
        assert is_ok(claim_result)
        assert claim_result.value.acquired
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        finalize_result = await repo.set_run_result(
            run_key="memory-sleep:2026-05-20",
            status=status,
            finished_at=finished_at,
            result_json={"status": status},
        )
        assert is_ok(finalize_result)
        assert finalize_result.value.status == status
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        record_result = await repo.get_by_run_key("memory-sleep:2026-05-20")
        assert is_ok(record_result)
        record = record_result.value
        assert record is not None
        assert record.status == status
        assert record.finished_at == finished_at
        assert record.result_json["status"] == status


@pytest.mark.anyio
async def test_memory_consolidation_run_repository_rejects_duplicate_claims(
    uow: IUnitOfWork,
) -> None:
    """Test that a terminal run cannot be claimed again."""

    started_at = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        claim_result = await repo.claim_run(
            run_key="memory-sleep:2026-05-21",
            job_name="memory_sleep",
            target_date=date(2026, 5, 21),
            started_at=started_at,
        )
        assert is_ok(claim_result)
        assert claim_result.value.acquired
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        finalize_result = await repo.set_run_result(
            run_key="memory-sleep:2026-05-21",
            status="skipped",
            finished_at=datetime(2026, 5, 21, 12, 10, tzinfo=UTC),
            result_json={"status": "skipped"},
        )
        assert is_ok(finalize_result)
        await uow.commit()

    async with uow:
        repo = uow.GetMemoryConsolidationRunRepository()
        duplicate_result = await repo.claim_run(
            run_key="memory-sleep:2026-05-21",
            job_name="memory_sleep",
            target_date=date(2026, 5, 21),
            started_at=datetime(2026, 5, 21, 12, 15, tzinfo=UTC),
        )
        assert is_ok(duplicate_result)
        assert not duplicate_result.value.acquired
        assert duplicate_result.value.record.status == "skipped"
