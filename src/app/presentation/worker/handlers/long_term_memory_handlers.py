"""Worker handlers for long-term memory organization."""

from datetime import time
from typing import Any, cast

from flow_med import Mediator

from app.presentation.worker.registry import scheduled_task
from app.usecases.memory.organize_long_term_memory import OrganizeLongTermMemoryCommand

LONG_TERM_MEMORY_INTERVAL_SECONDS = 2 * 24 * 60 * 60
LONG_TERM_MEMORY_RUN_TIME = time(hour=3)


@scheduled_task(interval_seconds=LONG_TERM_MEMORY_INTERVAL_SECONDS)
async def organize_long_term_memory_scheduled_task() -> None:
    """Run periodic long-term memory organization."""

    await Mediator.send_async(OrganizeLongTermMemoryCommand())


cast(Any, organize_long_term_memory_scheduled_task).schedule_run_time = (
    LONG_TERM_MEMORY_RUN_TIME
)
