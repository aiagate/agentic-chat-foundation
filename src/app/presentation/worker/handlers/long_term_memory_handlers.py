"""Worker handlers for long-term memory organization."""

from datetime import time
from typing import Any, cast
from zoneinfo import ZoneInfo

from flow_med import Mediator

from app.presentation.worker.registry import scheduled_task
from app.usecases.memory.consolidate_conversation_history import (
    ConsolidateConversationHistoryCommand,
)

LONG_TERM_MEMORY_INTERVAL_SECONDS = 24 * 60 * 60
LONG_TERM_MEMORY_RUN_TIME = time(hour=3, tzinfo=ZoneInfo("Asia/Tokyo"))


@scheduled_task(interval_seconds=LONG_TERM_MEMORY_INTERVAL_SECONDS)
async def consolidate_conversation_history_scheduled_task() -> None:
    """Run periodic conversation history consolidation."""

    await Mediator.send_async(ConsolidateConversationHistoryCommand())


cast(
    Any, consolidate_conversation_history_scheduled_task
).schedule_run_time = LONG_TERM_MEMORY_RUN_TIME
cast(Any, consolidate_conversation_history_scheduled_task).schedule_timezone = ZoneInfo(
    "Asia/Tokyo"
)
