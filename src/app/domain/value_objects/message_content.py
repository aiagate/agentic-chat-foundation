"""メッセージ内容を表す値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from flow_res import Err, Ok, Result


class MessageContentType(StrEnum):
    """対応するメッセージ種別。"""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    STICKER = "STICKER"
    EMOJI = "EMOJI"


@dataclass(frozen=True, slots=True)
class MessageContent:
    """単一メッセージの内容を表す。

    画像やスタンプのように、配信元ごとに異なるメタデータをそのまま保持する。
    """

    _type: MessageContentType
    _payload: dict[str, Any]

    @classmethod
    def text(cls, text: str) -> MessageContent:
        """テキストメッセージを生成する。"""
        return cls(_type=MessageContentType.TEXT, _payload={"text": text})

    @classmethod
    def image(cls, image_id: str, url: str | None = None) -> MessageContent:
        """画像メッセージを生成する。"""
        payload: dict[str, Any] = {"image_id": image_id}
        if url is not None:
            payload["url"] = url
        return cls(_type=MessageContentType.IMAGE, _payload=payload)

    @classmethod
    def sticker(cls, sticker_id: str, package_id: str | None = None) -> MessageContent:
        """スタンプメッセージを生成する。"""
        payload: dict[str, Any] = {"sticker_id": sticker_id}
        if package_id is not None:
            payload["package_id"] = package_id
        return cls(_type=MessageContentType.STICKER, _payload=payload)

    @classmethod
    def emoji(cls, emoji: str) -> MessageContent:
        """絵文字メッセージを生成する。"""
        return cls(_type=MessageContentType.EMOJI, _payload={"emoji": emoji})

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

        try:
            normalized_type = MessageContentType(content_type.upper())
        except ValueError:
            return Err(ValueError(f"Invalid message content type: {content_type}"))

        return Ok(cls(_type=normalized_type, _payload=payload.copy()))

    def to_primitive(self) -> dict[str, Any]:
        """永続化向けの辞書に変換する。"""
        return {
            "type": self._type.value,
            "payload": self._payload.copy(),
        }


MassageContent = MessageContent
