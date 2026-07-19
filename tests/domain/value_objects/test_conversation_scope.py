import pytest

from app.domain.value_objects.conversation_scope import ConversationScope


def test_conversation_scope_normalizes_channel_and_identifiers() -> None:
    scope = ConversationScope(
        user_id=" user-1 ",
        character_id=" reina ",
        channel=" DISCORD ",
        external_conversation_id=" channel-1 ",
    )

    assert scope.user_id == "user-1"
    assert scope.character_id == "reina"
    assert scope.channel == "discord"
    assert scope.external_conversation_id == "channel-1"


@pytest.mark.parametrize(
    "field_values",
    [
        {
            "user_id": "",
            "character_id": "reina",
            "channel": "discord",
            "external_conversation_id": "channel-1",
        },
        {
            "user_id": "user-1",
            "character_id": "",
            "channel": "discord",
            "external_conversation_id": "channel-1",
        },
        {
            "user_id": "user-1",
            "character_id": "reina",
            "channel": "web",
            "external_conversation_id": "channel-1",
        },
        {
            "user_id": "user-1",
            "character_id": "reina",
            "channel": "discord",
            "external_conversation_id": "",
        },
    ],
)
def test_conversation_scope_rejects_invalid_values(
    field_values: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        ConversationScope(**field_values)
