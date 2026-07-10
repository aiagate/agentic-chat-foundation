"""User event topics and payload builders."""

from typing import TypedDict

USER_CREATED_TOPIC = "user.created"


class UserCreatedPayload(TypedDict):
    """Payload emitted after a user is registered."""

    user_id: str


def build_user_created_payload(user_id: str) -> UserCreatedPayload:
    """Build the canonical user-created event payload."""
    return {"user_id": user_id}
