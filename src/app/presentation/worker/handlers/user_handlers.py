"""Worker handlers for user-related events."""

from typing import Any

from flow_med import Mediator

from app.presentation.worker.registry import event_handler
from app.usecases.users.welcome_user import WelcomeUserCommand


@event_handler("user.created")
async def on_user_created(payload: dict[str, Any]) -> None:
    """Handle user.created event."""

    user_id = payload.get("user_id")
    if not user_id:
        return

    await Mediator.send_async(WelcomeUserCommand(user_id=user_id))
