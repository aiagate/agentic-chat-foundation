"""Worker event handler registrations."""

from app.presentation.worker.handlers.chat_reply_handlers import (
    on_discord_chat_saved,
    on_line_chat_saved,
)
from app.presentation.worker.handlers.memory_sleep_handlers import (
    run_memory_sleep_scheduled_task,
)
from app.presentation.worker.handlers.search_handlers import (
    on_chat_search_completed,
    on_chat_search_requested,
)
from app.presentation.worker.handlers.user_handlers import on_user_created

__all__ = [
    "on_chat_search_completed",
    "on_chat_search_requested",
    "on_discord_chat_saved",
    "on_line_chat_saved",
    "on_user_created",
    "run_memory_sleep_scheduled_task",
]
