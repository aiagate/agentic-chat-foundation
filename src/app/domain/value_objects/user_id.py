"""ユーザー ID の値オブジェクト。"""

from dataclasses import dataclass

from app.domain.value_objects.base_id import BaseId


@dataclass(frozen=True)
class UserId(BaseId):
    """ULID ベースのユーザー ID。"""
