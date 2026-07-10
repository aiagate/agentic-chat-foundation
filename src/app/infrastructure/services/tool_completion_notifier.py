"""Event-bus implementation of tool completion notifications."""

from app.contracts.messages.chat_events import (
    CHAT_TOOL_COMPLETED_TOPIC,
    build_chat_tool_completed_payload,
)
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_completion_notifier import (
    IToolCompletionNotifier,
    ToolCompletionNotification,
)


class EventBusToolCompletionNotifier(IToolCompletionNotifier):
    """Translate normalized tool outcomes into completion events."""

    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus

    async def notify(self, notification: ToolCompletionNotification) -> None:
        await self._event_bus.publish(
            CHAT_TOOL_COMPLETED_TOPIC,
            build_chat_tool_completed_payload(
                chat_id=notification.chat_id,
                chat_type=notification.chat_type.to_primitive(),
                user_id=notification.user_id,
                status=notification.status,
                tool_name=notification.tool_name,
                continuation=notification.continuation,
                result=notification.result,
                error=notification.error,
                error_code=notification.error_code,
                guild_id=notification.guild_id,
                channel_id=notification.channel_id,
                agent_envelope=notification.agent_context,
            ),
        )
