"""Worker event handler registrations."""

from app.presentation.worker.handlers.agent_turn_handlers import on_agent_turn_requested
from app.presentation.worker.handlers.app_error_handlers import on_app_error_detected
from app.presentation.worker.handlers.chat_reply_handlers import (
    on_discord_chat_saved,
    on_line_chat_saved,
)
from app.presentation.worker.handlers.memory_sleep_handlers import (
    run_memory_sleep_scheduled_task,
)
from app.presentation.worker.handlers.outbox_handlers import dispatch_outbox_messages
from app.presentation.worker.handlers.tool_handlers import (
    on_chat_tool_completed,
    on_chat_tool_requested,
)
from app.presentation.worker.handlers.user_handlers import on_user_created

__all__ = [
    "on_app_error_detected",
    "on_agent_turn_requested",
    "on_chat_tool_completed",
    "on_chat_tool_requested",
    "on_discord_chat_saved",
    "on_line_chat_saved",
    "dispatch_outbox_messages",
    "on_user_created",
    "run_memory_sleep_scheduled_task",
]
