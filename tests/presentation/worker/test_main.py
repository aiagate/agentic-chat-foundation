"""Tests for worker entrypoint helpers."""

from datetime import UTC, datetime, time
from typing import Any, cast

from app.presentation.worker import __main__ as worker_main


def test_start_scheduled_tasks_uses_registered_tasks(
    monkeypatch: Any,
) -> None:
    """Test that the worker starts all scheduled tasks from the registry."""

    async def scheduled() -> None:
        return None

    task_sentinels: list[object] = []
    now = datetime(2026, 5, 19, 1, 0, tzinfo=UTC)
    cast(Any, scheduled).schedule_run_time = time(hour=3)

    def create_task_stub(coro: object) -> object:
        coroutine = cast(Any, coro)
        assert coroutine.cr_code.co_name == "_run_periodic_task"
        frame = coroutine.cr_frame
        assert frame is not None
        assert frame.f_locals["interval"] == 172800
        assert frame.f_locals["func"] is scheduled
        assert frame.f_locals["initial_delay_seconds"] == 7200.0
        coroutine.close()
        sentinel = object()
        task_sentinels.append(sentinel)
        return sentinel

    monkeypatch.setattr(worker_main.asyncio, "create_task", create_task_stub)

    registry = type(
        "RegistryStub",
        (),
        {
            "scheduled_tasks": [(172800, scheduled)],
        },
    )()

    tasks = worker_main._start_scheduled_tasks(cast(Any, registry), now=now)

    assert len(tasks) == 1
    assert tasks == task_sentinels


def test_initial_delay_until_run_returns_zero_before_target() -> None:
    """Test that the aligned delay is zero when it is time to run."""

    now = datetime(2026, 5, 19, 3, 0, tzinfo=UTC)

    assert worker_main._initial_delay_until_run(now, time(hour=3)) == 0.0


def test_start_invokes_async_main(monkeypatch: Any) -> None:
    """Test that the sync worker entry point runs the async main coroutine."""

    called: list[bool] = []

    async def fake_main() -> None:
        called.append(True)

    monkeypatch.setattr(worker_main, "main", fake_main)

    worker_main.start()

    assert called == [True]
