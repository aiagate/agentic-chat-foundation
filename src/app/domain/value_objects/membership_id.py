"""参加関係 ID の値オブジェクト。"""

from dataclasses import dataclass

from app.domain.value_objects.base_id import BaseId


@dataclass(frozen=True)
class MembershipId(BaseId):
    """ULID ベースの参加関係 ID。"""
