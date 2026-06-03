"""チーム参加時の役割を表す値オブジェクト。"""

from __future__ import annotations

from enum import Enum

from flow_res import Err, Ok, Result


class MembershipRole(str, Enum):
    """チームメンバーの役割。"""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"

    @classmethod
    def from_primitive(cls, value: str) -> Result[MembershipRole, ValueError]:
        """文字列から役割を復元する。"""
        try:
            normalized = value.strip()
            if not normalized:
                return Err(ValueError("Membership role cannot be empty."))
            return Ok(cls(normalized.upper()))
        except ValueError:
            return Err(ValueError(f"Invalid role: {value}"))
