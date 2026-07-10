"""Worker handlers for user-related events."""

from collections.abc import Mapping

from flow_med import Mediator

from app.contracts.messages.user_events import USER_CREATED_TOPIC
from app.presentation.worker.event_payloads import (
    UserCreatedPayload,
    parse_worker_event_payload,
)
from app.presentation.worker.registry import event_handler
from app.usecases.users.welcome_user import WelcomeUserCommand


@event_handler(USER_CREATED_TOPIC)
async def on_user_created(payload: Mapping[str, object]) -> None:
    """Handle user.created event."""

    event = parse_worker_event_payload(
        UserCreatedPayload,
        payload,
        event_name="user.created",
    )
    if event is None:
        return

    await Mediator.send_async(WelcomeUserCommand(user_id=event.user_id))
