"""Worker handlers for user-related events."""

from collections.abc import Mapping

from flow_med import Mediator

from app.presentation.worker.registry import event_handler
from app.usecases.users.welcome_user import WelcomeUserCommand


def _require_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


@event_handler("user.created")
async def on_user_created(payload: Mapping[str, object]) -> None:
    """Handle user.created event."""

    user_id = _require_str(payload, "user_id")
    if not user_id:
        return

    await Mediator.send_async(WelcomeUserCommand(user_id=user_id))
