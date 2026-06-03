"""チャット ID の値オブジェクト。"""

from dataclasses import dataclass

from app.domain.value_objects.base_id import BaseId


@dataclass(frozen=True)
class ChatId(BaseId):
    """ULID ベースのチャット ID。"""
