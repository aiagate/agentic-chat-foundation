import pytest

from app.domain.aggregates.user import User, UserChannelIdentity


def test_user_requires_a_valid_ulid() -> None:
    identity = UserChannelIdentity("discord", "external-user")

    with pytest.raises(ValueError, match="valid ULID"):
        User(id="x" * 26, identities=(identity,))


def test_user_accepts_a_valid_ulid() -> None:
    identity = UserChannelIdentity("discord", "external-user")

    user = User(
        id="01J00000000000000000000000",
        identities=(identity,),
    )

    assert user.id == "01J00000000000000000000000"
