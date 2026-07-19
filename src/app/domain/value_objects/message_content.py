"""メッセージ内容を表す値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from flow_res import Err, Ok, Result


class MessageContentType(StrEnum):
    """対応するメッセージ種別。"""

    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class MessageContent:
    """テキストメッセージの内容を表す。"""

    _type: MessageContentType
    _payload: dict[str, Any]

    @classmethod
    def text(cls, text: str) -> MessageContent:
        """テキストメッセージを生成する。"""
        return cls.texts([text])

    @classmethod
    def texts(cls, texts: list[str]) -> MessageContent:
        """複数テキストメッセージを生成する。"""
        normalized_texts = [text.strip() for text in texts if text.strip()]
        if not normalized_texts:
            raise ValueError("Message content cannot be empty")
        return cls(_type=MessageContentType.TEXT, _payload={"texts": normalized_texts})

    @property
    def type(self) -> MessageContentType:
        """メッセージ種別を返す。"""
        return self._type

    @property
    def payload(self) -> dict[str, Any]:
        """メッセージ内容のコピーを返す。"""
        return self._payload.copy()

    @classmethod
    def from_primitive(
        cls,
        value: dict[str, Any],
    ) -> Result[MessageContent, Exception]:
        """永続化データからメッセージ内容を復元する。"""
        content_type = value.get("type")
        payload = value.get("payload")

        if not isinstance(content_type, str):
            return Err(ValueError("Message content type must be a string."))
        if not isinstance(payload, dict):
            return Err(ValueError("Message content payload must be a dictionary."))

        if content_type.upper() != MessageContentType.TEXT.value:
            return Err(ValueError(f"Invalid message content type: {content_type}"))
        normalized_texts = _normalize_texts_payload(payload)
        if not normalized_texts:
            return Err(
                ValueError(
                    "Text message content payload must contain a non-empty texts list."
                )
            )
        return Ok(
            cls(_type=MessageContentType.TEXT, _payload={"texts": normalized_texts})
        )

    def to_primitive(self) -> dict[str, Any]:
        """永続化向けの辞書に変換する。"""
        return {
            "type": self._type.value,
            "payload": self._payload.copy(),
        }


def _normalize_texts_payload(payload: dict[str, Any]) -> list[str] | None:
    texts = payload.get("texts")
    if isinstance(texts, list):
        normalized_texts = [
            item.strip() for item in texts if isinstance(item, str) and item.strip()
        ]
        return normalized_texts
    return None


def render_message_content_text(
    payload: dict[str, Any],
    *,
    separator: str = "\n\n",
) -> str | None:
    """Render text-like payloads into a single string."""
    texts = _normalize_texts_payload(payload)
    if texts is None:
        return None
    return separator.join(texts)
