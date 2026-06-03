"""チーム参加状態を表す値オブジェクト。"""

from __future__ import annotations

from enum import Enum

from flow_res import Err, Ok, Result


class MembershipStatus(str, Enum):
    """チーム参加の状態。"""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    LEAVED = "LEAVED"

    @classmethod
    def from_primitive(cls, value: str) -> Result[MembershipStatus, ValueError]:
        """文字列から参加状態を復元する。"""
        try:
            return Ok(cls(value.upper()))
        except ValueError:
            return Err(ValueError(f"Invalid status: {value}"))
