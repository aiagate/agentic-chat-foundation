"""チャット種別の値オブジェクト。"""

from __future__ import annotations

from enum import StrEnum

from flow_res import Err, Ok, Result


class ChatType(StrEnum):
    """チャットプラットフォーム種別。"""

    DISCORD = "DISCORD"
    LINE = "LINE"

    @classmethod
    def from_primitive(cls, value: str) -> Result[ChatType, ValueError]:
        """文字列からチャット種別を復元する。

        Args:
            value: チャット種別の文字列表現。

        Returns:
            成功時は ChatType、失敗時は ValueError。
        """
        try:
            normalized = value.strip()
            if not normalized:
                return Err(ValueError("Chat type cannot be empty."))
            return Ok(cls(normalized.upper()))
        except ValueError:
            return Err(ValueError(f"Invalid chat type: {value}"))

    def to_primitive(self) -> str:
        """永続化向けの文字列に変換する。"""
        return self.value
