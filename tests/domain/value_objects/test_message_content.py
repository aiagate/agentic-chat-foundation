"""Tests for canonical message content values."""

from flow_res import is_err, is_ok

from app.domain.value_objects.message_content import (
    MessageContent,
    render_message_content_text,
)


def test_text_factory_uses_texts_payload() -> None:
    content = MessageContent.text("hello")

    assert content.to_primitive() == {
        "type": "TEXT",
        "payload": {"texts": ["hello"]},
    }


def test_from_primitive_accepts_only_canonical_text_payload() -> None:
    result = MessageContent.from_primitive(
        {"type": "TEXT", "payload": {"texts": ["hello", "follow-up"]}}
    )

    assert is_ok(result)
    assert result.value.payload == {"texts": ["hello", "follow-up"]}


def test_from_primitive_rejects_legacy_text_payload() -> None:
    result = MessageContent.from_primitive(
        {"type": "TEXT", "payload": {"text": "legacy"}}
    )

    assert is_err(result)


def test_text_factory_rejects_blank_content() -> None:
    try:
        MessageContent.text("   ")
    except ValueError as exc:
        assert str(exc) == "Message content cannot be empty"
    else:
        raise AssertionError("blank message content should be rejected")


def test_from_primitive_rejects_non_text_content() -> None:
    result = MessageContent.from_primitive(
        {"type": "IMAGE", "payload": {"image_id": "image-1"}}
    )

    assert is_err(result)


def test_render_message_content_text_does_not_accept_legacy_payload() -> None:
    assert render_message_content_text({"text": "legacy"}) is None
    assert render_message_content_text({"texts": ["hello", "follow-up"]}) == (
        "hello\n\nfollow-up"
    )
