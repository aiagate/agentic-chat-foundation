"""Worker handlers for memory sleep tasks."""

from datetime import time
from typing import Any, cast

from flow_med import Mediator

from app.presentation.worker.registry import scheduled_task
from app.usecases.memory.run_memory_sleep import RunMemorySleepCommand

MEMORY_SLEEP_INTERVAL_SECONDS = 2 * 24 * 60 * 60
MEMORY_SLEEP_RUN_TIME = time(hour=3)


@scheduled_task(interval_seconds=MEMORY_SLEEP_INTERVAL_SECONDS)
async def run_memory_sleep_scheduled_task() -> None:
    """Run the memory sleep job on a periodic schedule."""

    await Mediator.send_async(RunMemorySleepCommand())


cast(Any, run_memory_sleep_scheduled_task).schedule_run_time = MEMORY_SLEEP_RUN_TIME
